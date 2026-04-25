# EV Model Spec

This document specifies the behavior of:

- `ev/percentile calc v1.py`
- `ev/sell probablity model.py`

It is intended to make integration behavior explicit and reduce ambiguity when wiring outputs into backend/frontend code.

## 1) Scope

These modules estimate value and liquidity for a single `GrailedResultRow`:

- `percentile calc v1.py` computes a weighted price distribution, legacy edge metrics, and fee-adjusted profit metrics.
- `sell probablity model.py` estimates short-horizon probability of sale.

Both modules are pure compute modules with no network or database I/O.

## 2) Shared Input Shape

Both modules consume one row shaped like:

```python
{
  "live_listing": {...},
  "sold_comparables": [{...}, ...]
}
```

Expected fields used by these models:

- `live_listing.price.listing_price_usd`
- `live_listing.price.shipping_price_usd`
- `live_listing.designer`
- `live_listing.size`
- `live_listing.condition_raw`
- `live_listing.id`
- `live_listing.name`
- `sold_comparables[*].designer`
- `sold_comparables[*].size`
- `sold_comparables[*].condition_raw`
- `sold_comparables[*].sold_at_unix`
- `sold_comparables[*].price.sold_price_usd`
- `sold_comparables[*].price.shipping_price_usd`
- `sold_comparables[*].seller.reviews_count`
- `sold_comparables[*].seller.transactions_count`
- `sold_comparables[*].seller.badges.verified`
- `sold_comparables[*].seller.badges.trusted_seller`
- `sold_comparables[*].seller.posted_at_unix` (confidence percentage and sell probability model)

## 3) Percentile Valuation Model (`percentile calc v1.py`)

### 3.1 Core API

- `value_listing(row: Dict, scraped_at: int) -> Dict`
- `process_scrape(data: Dict) -> List[Dict]`

`process_scrape` iterates `data["results"]` and calls `value_listing` for each row, using `data["metadata"]["scraped_at_unix"]`.

### 3.2 Weighting Components

Comparable weight is a product of two terms:

`w = recency_weight * seller_score`

Definitions:

- `recency_weight = exp(-gamma * days_ago)`, `gamma=0.005`
- `seller_score = 0.8 + 0.2 * min(trust_factor, 1.0) + badge_bonus`

Only comparables with same designer are considered. Rows with `w <= 0.01` are dropped. Size, condition, and product/search similarity are expected to be hard-filtered before this model receives sold comparables.

### 3.3 Price Distribution

For each valid comparable:

- `sold_total = sold_price_usd + shipping_price_usd`

Weighted percentiles are computed from `(sold_total, w)`:

- `q10 = weighted_percentile(..., 10)`
- `q50 = weighted_percentile(..., 50)`
- `q90 = weighted_percentile(..., 90)`

Effective sample size uses Kish ESS:

- `effective_n = (sum(w)^2) / sum(w^2)`

Confidence percentage uses Kish ESS, percentile spread, and valid time-to-sell comp count:

- `sample_confidence = min(effective_n / 8, 1)`
- `spread = (q90 - q10) / q50`
- `spread_confidence = 1 / (1 + spread)`
- `liquidity_confidence = min(num_valid_time_comps / 8, 1)`
- `confidence_percentage = 100 * (0.35 * sample_confidence + 0.50 * spread_confidence + 0.15 * liquidity_confidence)`
- If `effective_n < 2`, cap `confidence_percentage` at `35`.
- Final value is rounded to one decimal place.

Valid time-to-sell comps use the same timestamp rule as the sell probability model: `sold_at_unix` and `seller.posted_at_unix` must both exist, and `0 < days_to_sell <= 365`.

If `q50 <= 0`, valuation returns no data instead of calculating confidence from an invalid denominator.

### 3.4 Output Contract

Success shape:

```python
{
  "id": str,
  "name": str,
  "cost": float,                # legacy compatibility: listing + shipping
  "listing_price": float,
  "buy_shipping_cost": float,
  "tax_amount": float,          # listing_price * 0.08875
  "sales_tax_rate": float,      # 0.08875
  "buy_cost": float,            # listing_price + tax_amount + buy_shipping_cost
  "dist": {
    "q10": float,
    "q50": float,
    "q90": float
  },
  "metrics": {
    "edge_usd": float,                       # legacy compatibility: q50 - cost
    "percent_under": float,                  # legacy compatibility: ((q50 - cost) / q50) * 100
    "expected_profit_grailed": float,         # grailed_net_payout - buy_cost
    "expected_profit_off_grailed": float,     # q50 - buy_cost
    "expected_profit_grailed_pct": float,     # expected_profit_grailed / buy_cost
    "expected_profit_off_grailed_pct": float, # expected_profit_off_grailed / buy_cost
    "grailed_total_fees": float,
    "grailed_net_payout": float,
    "effective_n": float,
    "confidence_percentage": float,
    "num_valid_price_comps": int,
    "num_valid_time_comps": int
  }
}
```

Fee-adjusted profit uses `q50` as the expected resale price. Buy-side sales tax uses New York City sales tax (`0.08875`) and applies only to the live listing price, not shipping. Grailed resale uses domestic seller fees by default: `9%` commission plus `3.49% + $0.49` processing fee, with resale shipping charged defaulting to `0`.

`edge_usd`, `percent_under`, and top-level `cost` are retained only for compatibility with existing callers. New ranking or display code should prefer `expected_profit_grailed` and `expected_profit_off_grailed`.

No-data shape (current behavior):

```python
{
  "id": str,
  "status": "no_data"
}
```

Note: this no-data path is intentionally documented here because it is a different schema than success output and needs handling downstream.

## 4) Sell Probability Model (`sell probablity model.py`)

### 4.1 Core API

- `estimate_sell_probability(row: Dict, horizon_days: int = 7, default_median_days: float = 21.0) -> Dict`

### 4.2 Time-to-Sell Estimation

For each sold comparable:

- `time_to_sell_days = (sold_at_unix - seller.posted_at_unix) / 86400`

Invalid values are discarded:

- `days <= 0`
- `days > 365`
- missing timestamps

`median_days` is median of valid values, or `default_median_days` if none exist.

### 4.3 Price Ratio Adjustment

- `live_price = live_listing.listing_price_usd + live_listing.shipping_price_usd`
- `q50_comp_price = median(sold_total_price over comps with price > 0)`
- `pricing_ratio = live_price / q50_comp_price` if valid, else `1.0`
- `adjusted_days = max(median_days * pricing_ratio, 1.0)`

### 4.4 Probability Mapping

- `raw_p_sell = horizon_days / adjusted_days`
- `p_sell = clamp(raw_p_sell, low=0.05, high=0.95)`

Output:

```python
{
  "p_sell": float,                # clamped [0.05, 0.95]
  "horizon_days": int,
  "median_days_to_sell": float,
  "adjusted_days_to_sell": float,
  "pricing_ratio": float,
  "live_price": float,
  "q50_comp_price": float | None,
  "num_valid_time_comps": int,
  "num_sold_comps": int
}
```

## 5) Integration Notes

- Distribution keys are `q10`, `q50`, `q90` and align with `shared.models.EVDistribution`.
- `q50` in valuation output and `q50_comp_price` in sell probability output represent related but not identical calculations (weighted percentile vs simple median over sold comps).
- Downstream callers should explicitly handle valuation no-data rows (`status == "no_data"`).

## 6) Non-Goals in Current Implementation

- No designer/category-specific confidence calibration beyond the global thin-market formula.
- No designer/category-specific hyperparameter tuning.
- No guarantee that output dicts fully conform to Pydantic models unless validated by caller.
