"""Wires the merged modules into two independent flows.

run_search: SearchParams -> SearchResponse  (scrape + EV + rank)
run_hype:   str          -> HypeResult      (Google Trends-native)

Both are pure orchestration. No I/O beyond what the underlying modules do.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ev import estimate_sell_probability, value_listing
from hype import related, score, trends
from scraper.scraper import scrape
from shared.models import (
    HypeEvidence,
    HypeResult,
    Recommendation,
    SearchParams,
    SearchResponse,
)
from shared.store import get_recommendations_store


async def run_search(params: SearchParams, *, persist: bool = True) -> SearchResponse:
    """Scrape, value, score, and rank.

    ``persist=True`` (default) writes fresh sold comparables through the
    configured ``ListingStore`` so the scraper's cache keeps growing across
    runs. Requires the store to be wired (see ``backend.main`` lifespan or
    ``backend.cli``).
    """
    scrape_result = await scrape(params, persist=persist)
    scraped_at = scrape_result.metadata.scraped_at_unix

    items: list[Recommendation] = []
    for row in scrape_result.results:
        row_dict = row.model_dump(mode="json")
        valuation = value_listing(row_dict, scraped_at)
        if valuation.get("status") == "no_data":
            continue
        sell_prob = estimate_sell_probability(row_dict)
        metrics = valuation["metrics"]
        items.append(
            Recommendation(
                item_id=row.live_listing.id,
                scraped_at_unix=scraped_at,
                query=params.query,
                edge_usd=metrics["edge_usd"],
                p_sell=sell_prob["p_sell"],
                q50=valuation["dist"]["q50"],
                cost=valuation["cost"],
                confidence=metrics["confidence"],
                valuation=valuation,
                sell_probability=sell_prob,
                live_listing=row.live_listing,
            )
        )

    items.sort(key=lambda r: r.p_sell * r.edge_usd, reverse=True)

    response = SearchResponse(metadata=scrape_result.metadata, items=items)
    if persist:
        store = get_recommendations_store()
        if store is not None:
            store.save_recommendations(response=response, params=params)
    return response


async def run_hype(term: str) -> HypeResult:
    """Fetch 30d/7d/90d series + related queries in parallel, compute score."""
    series_30d, series_7d, series_90d, related_items = await asyncio.gather(
        asyncio.to_thread(trends.fetch, term, "30d"),
        asyncio.to_thread(trends.fetch, term, "7d"),
        asyncio.to_thread(trends.fetch, term, "90d"),
        asyncio.to_thread(related.fetch, term),
    )

    score_value, confidence = score.compute(series_30d.points)

    return HypeResult(
        term=term,
        score=score_value,
        confidence=confidence,
        series_30d=series_30d,
        series_7d=series_7d,
        series_90d=series_90d,
        evidence=HypeEvidence(related=related_items),
        fetched_at_unix=int(datetime.now(tz=UTC).timestamp()),
    )