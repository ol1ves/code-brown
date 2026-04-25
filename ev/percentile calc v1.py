import math
from typing import Dict, List
import numpy as np

SECONDS_PER_DAY = 86400

# -----------------------------
# 1. Individual Weighting Components
# -----------------------------

def get_recency_weight(sold_unix: int, current_unix: int, gamma: float = 0.005) -> float:
    """Decays weight based on days since sale (approx 0.6x weight at 100 days)"""
    days_ago = max((current_unix - sold_unix) / 86400, 0)
    return math.exp(-gamma * days_ago)

def get_seller_score(seller: Dict) -> float:
    """Weights high-trust professional sellers more as they represent true market peak."""
    revs = seller.get("reviews_count", 0) or 0
    txns = seller.get("transactions_count", 0) or 0
    badges = seller.get("badges", {}) or {}
    
    # Log scaling: 10 vs 100 matters more than 1000 vs 1090
    trust_factor = (math.log1p(revs) / 6.0) + (math.log1p(txns) / 7.0)
    badge_bonus = 0.2 if badges.get("trusted_seller") or badges.get("verified") else 0.0
    
    return 0.8 + (min(trust_factor, 1.0) * 0.2) + badge_bonus

# -----------------------------
# 2. Statistical Core
# -----------------------------

def weighted_percentile(values: List[float], weights: List[float], p: float) -> float:
    """Calculates the weighted p-th percentile."""
    v, w = np.array(values), np.array(weights)
    idx = np.argsort(v)
    v, w = v[idx], w[idx]
    cum_w = np.cumsum(w)
    cutoff = (p / 100.0) * cum_w[-1]
    return float(v[np.searchsorted(cum_w, cutoff)])

def get_effective_n(weights: List[float]) -> float:
    """Kish's Effective Sample Size: measures data quality/density."""
    w = np.array(weights)
    if np.sum(w) == 0: return 0
    return float((np.sum(w)**2) / np.sum(w**2))

def has_valid_time_to_sell(comp: Dict) -> bool:
    sold_at = comp.get("sold_at_unix")
    seller = comp.get("seller", {}) or {}
    posted_at = seller.get("posted_at_unix")

    if sold_at is None or posted_at is None:
        return False

    days = (sold_at - posted_at) / SECONDS_PER_DAY
    return 0 < days <= 365

def get_confidence_percentage(
    effective_n: float,
    q10: float,
    q50: float,
    q90: float,
    num_valid_time_comps: int,
) -> float:
    sample_confidence = min(effective_n / 8, 1)
    spread = (q90 - q10) / q50
    spread_confidence = 1 / (1 + spread)
    liquidity_confidence = min(num_valid_time_comps / 8, 1)

    confidence_percentage = 100 * (
        0.35 * sample_confidence
        + 0.50 * spread_confidence
        + 0.15 * liquidity_confidence
    )

    if effective_n < 2:
        confidence_percentage = min(confidence_percentage, 35)

    return round(confidence_percentage, 1)

# -----------------------------
# 3. The Appraisal Engine
# -----------------------------

def value_listing(row: Dict, scraped_at: int) -> Dict:
    live = row["live_listing"]
    comps = row.get("sold_comparables", [])
    
    # Calculate Live All-In Cost
    live_price = live["price"]["listing_price_usd"]
    live_ship = live["price"]["shipping_price_usd"]
    total_cost = live_price + live_ship

    prices, weights = [], []
    num_valid_time_comps = 0

    for comp in comps:
        # 1. Hard Filter: Designer must match
        if comp.get("designer", "").lower() != live.get("designer", "").lower():
            continue

        if has_valid_time_to_sell(comp):
            num_valid_time_comps += 1
        
        # 2. Extract All-In Sold Price
        sold_total = comp["price"]["sold_price_usd"] + comp["price"]["shipping_price_usd"]
        
        # 3. Calculate Aggregate Weight
        w = get_recency_weight(comp["sold_at_unix"], scraped_at) * get_seller_score(comp["seller"])
        
        if w > 0.01: # Filter out irrelevant noise
            prices.append(sold_total)
            weights.append(w)

    if not prices:
        return {"id": live["id"], "status": "no_data"}

    # Calculate Distribution
    p10 = weighted_percentile(prices, weights, 10)
    p50 = weighted_percentile(prices, weights, 50)
    p90 = weighted_percentile(prices, weights, 90)
    eff_n = get_effective_n(weights)

    if p50 <= 0:
        return {"id": live["id"], "status": "no_data"}

    confidence_percentage = get_confidence_percentage(
        eff_n,
        p10,
        p50,
        p90,
        num_valid_time_comps,
    )

    return {
        "id": live["id"],
        "name": live["name"],
        "cost": total_cost,
        "dist": {
            "q10": round(p10, 2),
            "q50": round(p50, 2),
            "q90": round(p90, 2)
        },
        "metrics": {
            "edge_usd": round(p50 - total_cost, 2),
            "percent_under": round(((p50 - total_cost) / p50) * 100, 1),
            "effective_n": round(eff_n, 1),
            "confidence_percentage": confidence_percentage,
            "num_valid_price_comps": len(prices),
            "num_valid_time_comps": num_valid_time_comps
        }
    }

# -----------------------------
# 4. Main Entry Point
# -----------------------------

def process_scrape(data: Dict) -> List[Dict]:
    scraped_at = data["metadata"]["scraped_at_unix"]
    results = []
    for row in data["results"]:
        results.append(value_listing(row, scraped_at))
    return results
