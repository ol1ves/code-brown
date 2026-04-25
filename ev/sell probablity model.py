from typing import Dict, List, Optional
import statistics
import math
import time


SECONDS_PER_DAY = 86400


def clamp(x: float, low: float = 0.05, high: float = 0.95) -> float:
    return max(low, min(high, x))


def get_listing_price(live_listing: Dict) -> float:
    price = live_listing.get("price", {})
    return float(price.get("listing_price_usd", 0) + price.get("shipping_price_usd", 0))


def get_sold_total_price(sold_listing: Dict) -> float:
    price = sold_listing.get("price", {})
    return float(price.get("sold_price_usd", 0) + price.get("shipping_price_usd", 0))


def compute_time_to_sell_days(sold_listing: Dict) -> Optional[float]:
    sold_at = sold_listing.get("sold_at_unix")
    seller = sold_listing.get("seller", {})
    posted_at = seller.get("posted_at_unix")

    if sold_at is None or posted_at is None:
        return None

    days = (sold_at - posted_at) / SECONDS_PER_DAY

    # filter impossible/bad data
    if days <= 0 or days > 365:
        return None

    return days


def compute_q50_from_sold_comps(sold_comparables: List[Dict]) -> Optional[float]:
    prices = [
        get_sold_total_price(comp)
        for comp in sold_comparables
        if get_sold_total_price(comp) > 0
    ]

    if len(prices) == 0:
        return None

    return statistics.median(prices)


def estimate_sell_probability(
    row: Dict,
    horizon_days: int = 7,
    default_median_days: float = 21.0,
) -> Dict:
    """
    Estimates P(sell within horizon_days) for one GrailedResultRow.

    Uses:
    - sold comparables' time-to-sell
    - live listing price vs sold comp median price

    row structure:
    {
        "live_listing": {...},
        "sold_comparables": [...]
    }
    """

    live = row["live_listing"]
    comps = row.get("sold_comparables", [])

    # 1. compute comp time-to-sell values
    times = []
    for comp in comps:
        d = compute_time_to_sell_days(comp)
        if d is not None:
            times.append(d)

    if len(times) > 0:
        median_days = statistics.median(times)
    else:
        median_days = default_median_days

    # 2. compute pricing ratio
    live_price = get_listing_price(live)
    q50 = compute_q50_from_sold_comps(comps)

    if q50 is None or q50 <= 0:
        pricing_ratio = 1.0
    else:
        pricing_ratio = live_price / q50

    # 3. adjust expected selling time by pricing ratio
    adjusted_days = median_days * pricing_ratio

    # avoid division weirdness
    adjusted_days = max(adjusted_days, 1.0)

    # 4. convert adjusted time into probability
    raw_p_sell = horizon_days / adjusted_days

    # 5. clamp probability
    p_sell = clamp(raw_p_sell)

    return {
        "p_sell": p_sell,
        "horizon_days": horizon_days,
        "median_days_to_sell": median_days,
        "adjusted_days_to_sell": adjusted_days,
        "pricing_ratio": pricing_ratio,
        "live_price": live_price,
        "q50_comp_price": q50,
        "num_valid_time_comps": len(times),
        "num_sold_comps": len(comps),
    }
