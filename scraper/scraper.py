"""Grailed scraper. Backend wires a ``ListingStore`` via ``set_store`` at boot;
``scrape`` accepts ``SearchParams`` and returns a structured ``GrailedScrapeResult``.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from scraper.algolia import (
    build_search_payload,
    build_seller_stats_payload,
    build_sold_comparable_payload,
    extract_hits,
    extract_results_in_order,
    hit_user_id,
    parse_live_hit,
    parse_seller_stats,
    parse_sold_hit,
)
from scraper.client import GrailedClient
from scraper.config import (
    ALGOLIA_LIVE_INDEX,
    ALGOLIA_SOLD_INDEX,
    ALGOLIA_SEARCH_URL,
    get_algolia_headers,
)
from shared.models import (
    GrailedResultRow,
    GrailedScrapeResult,
    ScrapeMetadata,
    SearchParams,
    SoldListing,
)

if TYPE_CHECKING:
    from shared.store import ListingStore

_store: "ListingStore | None" = None


def set_store(store: "ListingStore") -> None:
    """Called once from backend lifespan. Scraper must not construct the store."""
    global _store
    _store = store


def _get_store() -> "ListingStore":
    if _store is None:
        raise RuntimeError("ListingStore not configured; call set_store at app boot")
    return _store


def save_listing(listing: dict) -> None:
    """Upsert one sold listing. ``listing`` must include ``id`` and ``category``."""
    _get_store().save_listing(listing)


def has_listing(item_id: str) -> bool:
    """Cheap dedup check before scrape."""
    return _get_store().has_listing(item_id)


def _to_sold_row(listing: SoldListing, *, category: str) -> dict:
    payload = listing.model_dump(mode="json")
    payload["category"] = category
    return payload


def _persist_sold(listing: SoldListing, *, category: str) -> None:
    _get_store().save_listing(_to_sold_row(listing, category=category))


async def scrape(
    params: SearchParams, *, persist: bool = False
) -> GrailedScrapeResult:
    """Run a Grailed scrape against Algolia. Returns structured results.

    ``persist=True`` upserts each sold comparable through the configured
    ``ListingStore``; raises if no store wired.
    """
    async with GrailedClient() as client:
        live_hits = await _search_live(client, params)
        live_hits = live_hits[: params.live_limit]

        sold_hits_per_live: list[list[dict[str, Any]]] = []
        if params.include_sold:
            sold_hits_per_live = await _search_sold_for_each(client, live_hits, params)

        cached_per_live, uncached_per_live = _partition_sold_by_cache(
            sold_hits_per_live, use_cache=persist and _store is not None
        )

        seller_stats = await _fetch_seller_stats(client, live_hits, uncached_per_live)

        descriptions: dict[str, str] = {}
        if params.fetch_descriptions:
            descriptions = await _fetch_descriptions(
                client, live_hits, uncached_per_live
            )

        live_listings = [
            parse_live_hit(h, seller_stats, descriptions) for h in live_hits
        ]

        rows: list[GrailedResultRow] = []
        for live, uncached_hits, cached in zip(
            live_listings,
            uncached_per_live or [[] for _ in live_listings],
            cached_per_live or [[] for _ in live_listings],
        ):
            fresh = [parse_sold_hit(h, seller_stats, descriptions) for h in uncached_hits]
            if persist and fresh:
                category = params.category or params.department or "unknown"
                for s in fresh:
                    _persist_sold(s, category=category)
            rows.append(GrailedResultRow(live_listing=live, sold_comparables=cached + fresh))

    metadata = ScrapeMetadata(
        query=params.query,
        categories=[v for v in (params.department, params.category) if v],
        live_limit_requested=params.live_limit,
        sold_limit_requested=params.sold_limit,
        scraped_at_unix=int(time.time()),
        total_live_found=len(live_listings),
    )
    return GrailedScrapeResult(metadata=metadata, results=rows)


async def _search_live(
    client: GrailedClient, params: SearchParams
) -> list[dict[str, Any]]:
    payload = build_search_payload(params, ALGOLIA_LIVE_INDEX)
    raw = await client.post_json(
        ALGOLIA_SEARCH_URL,
        payload,
        headers=get_algolia_headers(),
        throttle=False,
    )
    return extract_hits(raw)


async def _search_sold_for_each(
    client: GrailedClient, live_hits: list[dict[str, Any]], params: SearchParams
) -> list[list[dict[str, Any]]]:
    """Batch all sold-comparable queries into one Algolia multi-query POST."""
    if not live_hits:
        return []
    merged_requests: list[dict[str, Any]] = []
    for hit in live_hits:
        payload = build_sold_comparable_payload(hit, params, ALGOLIA_SOLD_INDEX)
        merged_requests.extend(payload["requests"])
    raw = await client.post_json(
        ALGOLIA_SEARCH_URL,
        {"requests": merged_requests},
        headers=get_algolia_headers(),
        throttle=False,
    )
    results = extract_results_in_order(raw, len(live_hits))
    out: list[list[dict[str, Any]]] = []
    for result in results:
        hits = result.get("hits") if isinstance(result, dict) else None
        if not isinstance(hits, list):
            out.append([])
            continue
        sold = [h for h in hits if isinstance(h, dict)][: params.sold_limit]
        out.append(sold)
    return out


def _partition_sold_by_cache(
    sold_hits_per_live: list[list[dict[str, Any]]], *, use_cache: bool
) -> tuple[list[list[SoldListing]], list[list[dict[str, Any]]]]:
    """For each live listing's sold hits, split into (cached, uncached).

    Cached: ID already in store — load full SoldListing from DB, skip Algolia
    re-parse and downstream seller_stats/description fetches.
    Uncached: parse fresh from Algolia hit and (optionally) persist later.
    ``use_cache=False`` short-circuits: everything treated as uncached.
    """
    cached_per_live: list[list[SoldListing]] = []
    uncached_per_live: list[list[dict[str, Any]]] = []
    store = _store if use_cache else None
    for hits in sold_hits_per_live:
        cached: list[SoldListing] = []
        uncached: list[dict[str, Any]] = []
        for h in hits:
            hid = str(h.get("id") or h.get("objectID") or "")
            if store and hid and store.has_listing(hid):
                row = store.get_listing(hid)
                if row:
                    cached.append(SoldListing.model_validate(row))
                    continue
            uncached.append(h)
        cached_per_live.append(cached)
        uncached_per_live.append(uncached)
    return cached_per_live, uncached_per_live


async def _fetch_descriptions(
    client: GrailedClient,
    live_hits: list[dict[str, Any]],
    sold_hits_per_live: list[list[dict[str, Any]]],
) -> dict[str, str]:
    """Fetch listing detail per id and extract description. Failures yield ''."""
    listing_ids: list[str] = []
    seen: set[str] = set()
    for h in live_hits:
        lid = str(h.get("id") or h.get("objectID") or "")
        if lid and lid not in seen:
            seen.add(lid)
            listing_ids.append(lid)
    for batch in sold_hits_per_live:
        for h in batch:
            lid = str(h.get("id") or h.get("objectID") or "")
            if lid and lid not in seen:
                seen.add(lid)
                listing_ids.append(lid)

    if not listing_ids:
        return {}

    async def fetch_one(lid: str) -> tuple[str, str]:
        try:
            raw = await client.get_listing_detail(lid)
        except Exception:
            return lid, ""
        inner = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
        desc = inner.get("description") if isinstance(inner, dict) else None
        return lid, str(desc) if isinstance(desc, str) else ""

    results = await asyncio.gather(*(fetch_one(i) for i in listing_ids))
    return dict(results)


async def _fetch_seller_stats(
    client: GrailedClient,
    live_hits: list[dict[str, Any]],
    sold_hits_per_live: list[list[dict[str, Any]]],
) -> dict[int, tuple[int, int]]:
    """For each unique seller across live + sold hits, fetch (items_for_sale_count,
    posted_at_unix). Single Algolia query per unique user_id."""
    user_ids: set[int] = set()
    for h in live_hits:
        uid = hit_user_id(h)
        if uid is not None:
            user_ids.add(uid)
    for batch in sold_hits_per_live:
        for h in batch:
            uid = hit_user_id(h)
            if uid is not None:
                user_ids.add(uid)

    if not user_ids:
        return {}

    ordered_uids = list(user_ids)
    merged_requests: list[dict[str, Any]] = []
    for uid in ordered_uids:
        payload = build_seller_stats_payload(uid, ALGOLIA_LIVE_INDEX)
        merged_requests.extend(payload["requests"])
    raw = await client.post_json(
        ALGOLIA_SEARCH_URL,
        {"requests": merged_requests},
        headers=get_algolia_headers(),
        throttle=False,
    )
    results = extract_results_in_order(raw, len(ordered_uids))
    return {
        uid: parse_seller_stats({"results": [result]})
        for uid, result in zip(ordered_uids, results)
    }
