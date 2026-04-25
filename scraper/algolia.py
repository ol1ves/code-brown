"""Algolia request building and hit-to-model parsing for Grailed."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from scraper.config import ALGOLIA_FACETS
from scraper.exceptions import SchemaValidationError
from shared.models import SearchParams, SoldListing, LiveListing


def build_search_payload(params: SearchParams, index_name: str) -> dict[str, Any]:
    """Build the Algolia multi-query payload for one index."""
    return {
        "requests": [
            {
                "indexName": index_name,
                "params": _encode_params(params),
            }
        ]
    }


def build_sold_comparable_payload(
    live_hit: dict[str, Any], params: SearchParams, index_name: str
) -> dict[str, Any]:
    """Search the sold index for comparables of a given live listing.

    Narrows match by carrying the live hit's category, condition, size, and
    color into the sold query. Size and color have no clean Algolia facet, so
    they are folded into the query text. Tighter filters mean some live
    listings yield very few sold comparables — acceptable: arbitrage targets
    are the items that *do* surface dense sold history.
    """
    name = str(live_hit.get("title") or "")
    designer = _extract_designer(live_hit)
    size = str(live_hit.get("size") or "")
    color = str(live_hit.get("color") or "")
    condition = str(live_hit.get("condition") or "")
    category = str(live_hit.get("category") or "")
    category_path = str(live_hit.get("category_path") or "")
    department = str(live_hit.get("department") or "")

    query_parts = [p for p in (name, color, size) if p]
    derived = params.model_copy(
        update={
            "query": " ".join(query_parts),
            "designer": designer or params.designer,
            "condition": condition or params.condition,
            "category": category or params.category,
            "category_path": category_path or params.category_path,
            "department": department or params.department,
            "live_limit": params.sold_limit,
        }
    )
    return build_search_payload(derived, index_name)


def extract_hits(raw: dict[str, Any]) -> list[dict[str, Any]]:
    results = raw.get("results")
    if not isinstance(results, list) or not results:
        raise SchemaValidationError("Algolia response missing 'results'")
    hits = results[0].get("hits")
    if not isinstance(hits, list):
        raise SchemaValidationError("Algolia results[0] missing 'hits'")
    return [h for h in hits if isinstance(h, dict)]


def extract_hits_per_request(
    raw: dict[str, Any], n_requests: int
) -> list[list[dict[str, Any]]]:
    """Multi-query response → list of hit-lists, one per request in send order."""
    results = raw.get("results")
    if not isinstance(results, list):
        raise SchemaValidationError("Algolia response missing 'results'")
    out: list[list[dict[str, Any]]] = []
    for i in range(n_requests):
        result = results[i] if i < len(results) else {}
        hits = result.get("hits") if isinstance(result, dict) else None
        out.append([h for h in hits if isinstance(h, dict)] if isinstance(hits, list) else [])
    return out


def extract_results_in_order(raw: dict[str, Any], n: int) -> list[dict[str, Any]]:
    """Multi-query response → list of raw result dicts, padded to ``n`` entries."""
    results = raw.get("results")
    if not isinstance(results, list):
        raise SchemaValidationError("Algolia response missing 'results'")
    return [
        results[i] if i < len(results) and isinstance(results[i], dict) else {}
        for i in range(n)
    ]


def parse_live_hit(
    hit: dict[str, Any],
    seller_stats: dict[int, tuple[int, int]] | None = None,
    descriptions: dict[str, str] | None = None,
) -> LiveListing:
    payload = _base_payload(hit, seller_stats)
    if descriptions:
        payload["description"] = descriptions.get(payload["id"], "")
    return LiveListing.model_validate(payload)


def parse_sold_hit(
    hit: dict[str, Any],
    seller_stats: dict[int, tuple[int, int]] | None = None,
    descriptions: dict[str, str] | None = None,
) -> SoldListing:
    payload = _base_payload(hit, seller_stats)
    if descriptions:
        payload["description"] = descriptions.get(payload["id"], "")
    payload["price"] = {
        "sold_price_usd": _coerce_int(hit.get("sold_price") or hit.get("price_i")),
        "shipping_price_usd": _coerce_int(hit.get("sold_shipping_price")),
    }
    payload["sold_at_unix"] = _coerce_int(hit.get("sold_at_i"))
    return SoldListing.model_validate(payload)


def hit_user_id(hit: dict[str, Any]) -> int | None:
    user = hit.get("user")
    if not isinstance(user, dict):
        return None
    uid = user.get("id")
    try:
        return int(uid) if uid is not None else None
    except (TypeError, ValueError):
        return None


def build_seller_stats_payload(user_id: int, index_name: str) -> dict[str, Any]:
    """Single Algolia call yielding nbHits (items_for_sale_count) and the oldest
    created_at_i across *all* matching listings via facet stats.

    ``hitsPerPage=0`` ships no documents; ``facets=["created_at_i"]`` makes
    Algolia return min/max/avg/sum across the full match set, not just the
    1000-doc page. Smaller payload, more accurate posted_at_unix.
    """
    encoded = urlencode(
        {
            "filters": f"user.id:{user_id}",
            "hitsPerPage": "0",
            "page": "0",
            "facets": json.dumps(["created_at_i"]),
            "attributesToRetrieve": json.dumps([]),
            "attributesToHighlight": json.dumps([]),
        }
    )
    return {"requests": [{"indexName": index_name, "params": encoded}]}


def parse_seller_stats(raw: dict[str, Any]) -> tuple[int, int]:
    """Returns (items_for_sale_count, posted_at_unix)."""
    results = raw.get("results")
    if not isinstance(results, list) or not results:
        return (0, 0)
    res = results[0]
    if not isinstance(res, dict):
        return (0, 0)
    nb_hits = _coerce_int(res.get("nbHits"))
    posted_at = 0
    facets_stats = res.get("facets_stats")
    if isinstance(facets_stats, dict):
        ts_stats = facets_stats.get("created_at_i")
        if isinstance(ts_stats, dict):
            posted_at = _coerce_int(ts_stats.get("min"))
    return (nb_hits, posted_at)


def _encode_params(params: SearchParams) -> str:
    facet_filters: list[list[str]] = []
    if params.department:
        facet_filters.append([f"department:{params.department}"])
    if params.category:
        facet_filters.append([f"category:{params.category}"])
    if params.category_path:
        facet_filters.append([f"category_path:{params.category_path}"])
    if params.condition:
        facet_filters.append([f"condition:{params.condition}"])
    if params.location:
        facet_filters.append([f"location:{params.location}"])
    if params.strata:
        facet_filters.append([f"strata:{params.strata}"])
    if params.designer:
        facet_filters.append([f"designers.name:{params.designer}"])

    encoded = {
        "analytics": "false",
        "clickAnalytics": "false",
        "enableABTest": "false",
        "enablePersonalization": "false",
        "facetFilters": json.dumps(facet_filters),
        "facets": json.dumps(ALGOLIA_FACETS),
        "filters": "",
        "highlightPostTag": "</ais-highlight-0000000000>",
        "highlightPreTag": "<ais-highlight-0000000000>",
        "hitsPerPage": str(max(1, params.live_limit)),
        "maxValuesPerFacet": "200",
        "numericFilters": json.dumps(
            [f"price_i>={params.min_price_usd}", f"price_i<={params.max_price_usd}"]
        ),
        "page": "0",
        "personalizationImpact": "0",
        "query": params.query or "",
    }
    return urlencode(encoded)


def _base_payload(
    hit: dict[str, Any],
    seller_stats: dict[int, tuple[int, int]] | None = None,
) -> dict[str, Any]:
    listing_id = str(hit.get("id") or hit.get("objectID") or "")
    if not listing_id:
        raise SchemaValidationError("hit missing id/objectID")

    user_obj = hit.get("user") or {}
    seller = _extract_seller(user_obj)
    if seller_stats:
        uid = user_obj.get("id") if isinstance(user_obj, dict) else None
        try:
            uid_int = int(uid) if uid is not None else None
        except (TypeError, ValueError):
            uid_int = None
        if uid_int is not None and uid_int in seller_stats:
            items_count, posted_at = seller_stats[uid_int]
            seller["items_for_sale_count"] = items_count
            seller["posted_at_unix"] = posted_at
    return {
        "id": listing_id,
        "url": f"https://www.grailed.com/listings/{listing_id}",
        "designer": _extract_designer(hit),
        "name": str(hit.get("title") or ""),
        "size": str(hit.get("size") or ""),
        "condition_raw": str(hit.get("condition") or ""),
        "location": str(hit.get("location") or ""),
        "color": str(hit.get("color") or ""),
        "image_urls": _extract_image_urls(hit),
        "price": {
            "listing_price_usd": _coerce_int(hit.get("price_i") or hit.get("price")),
            "shipping_price_usd": _coerce_int(hit.get("shipping")),
        },
        "seller": seller,
        "description": "",
    }


def _extract_designer(hit: dict[str, Any]) -> str:
    name = hit.get("designer_names")
    if isinstance(name, str) and name:
        return name
    designers = hit.get("designers")
    if isinstance(designers, list) and designers:
        first = designers[0]
        if isinstance(first, dict) and first.get("name"):
            return str(first["name"])
    return ""


def _extract_image_urls(hit: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    cover = hit.get("cover_photo")
    if isinstance(cover, dict):
        for key in ("url", "image_url"):
            value = cover.get(key)
            if isinstance(value, str) and value:
                urls.append(value)
                break
    photos = hit.get("photos")
    if isinstance(photos, list):
        for item in photos:
            if isinstance(item, dict):
                value = item.get("url") or item.get("image_url")
                if isinstance(value, str) and value:
                    urls.append(value)
    return urls


def _extract_seller(user: dict[str, Any]) -> dict[str, Any]:
    seller_score = user.get("seller_score") or {}
    return {
        "seller_name": str(user.get("username") or ""),
        "reviews_count": _coerce_int(
            seller_score.get("rating_count") if isinstance(seller_score, dict) else 0
        ),
        "transactions_count": _coerce_int(user.get("total_bought_and_sold")),
        "items_for_sale_count": _coerce_int(user.get("listings_for_sale_count")),
        "posted_at_unix": _coerce_int(user.get("created_at_i")),
        "badges": {
            "verified": bool(user.get("verified", False)),
            "trusted_seller": bool(user.get("trusted_seller", False)),
            "quick_responder": bool(user.get("quick_responder", False)),
            "speedy_shipper": bool(user.get("speedy_shipper", False)),
        },
    }


def _coerce_int(value: Any) -> int:
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
