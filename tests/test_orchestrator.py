from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from backend import orchestrator
from shared import store as store_mod
from shared.models import (
    GrailedResultRow,
    GrailedScrapeResult,
    HypeEvidence,
    LiveListing,
    LivePrice,
    RelatedQuery,
    ScrapeMetadata,
    SearchParams,
    Seller,
    SellerBadges,
    SoldListing,
    SoldPrice,
    TrendPoint,
    TrendSeries,
)


def _seller() -> Seller:
    return Seller(
        seller_name="tester",
        reviews_count=10,
        transactions_count=20,
        items_for_sale_count=3,
        posted_at_unix=1700000000,
        badges=SellerBadges(
            verified=True,
            trusted_seller=False,
            quick_responder=False,
            speedy_shipper=False,
        ),
    )


def _live(listing_id: str) -> LiveListing:
    return LiveListing(
        id=listing_id,
        url=f"https://www.grailed.com/listings/{listing_id}",
        designer="Guidi",
        name=f"Boot {listing_id}",
        size="43",
        condition_raw="Gently Used",
        location="US",
        color="Black",
        image_urls=[],
        price=LivePrice(listing_price_usd=700, shipping_price_usd=25),
        seller=_seller(),
        description="desc",
    )


def _sold(listing_id: str) -> SoldListing:
    return SoldListing(
        id=f"sold-{listing_id}",
        url=f"https://www.grailed.com/listings/sold-{listing_id}",
        designer="Guidi",
        name=f"Sold Boot {listing_id}",
        size="43",
        condition_raw="Used",
        location="US",
        color="Black",
        image_urls=[],
        price=SoldPrice(sold_price_usd=650, shipping_price_usd=20),
        sold_at_unix=1700000500,
        seller=_seller(),
        description="desc",
    )


def _row(row_id: str) -> GrailedResultRow:
    return GrailedResultRow(live_listing=_live(row_id), sold_comparables=[_sold(row_id)])


def _scrape_result(row_ids: list[str]) -> GrailedScrapeResult:
    metadata = ScrapeMetadata(
        query="guidi",
        categories=["menswear"],
        live_limit_requested=5,
        sold_limit_requested=3,
        scraped_at_unix=1713995645,
        total_live_found=len(row_ids),
    )
    return GrailedScrapeResult(metadata=metadata, results=[_row(i) for i in row_ids])


def _valuation(
    edge_usd: float,
    *,
    confidence: str | None = "medium",
    confidence_percentage: float | None = None,
) -> dict:
    q50 = 700.0
    metrics = {
        "edge_usd": edge_usd,
        "percent_under": (edge_usd / q50) * 100,
        "effective_n": 4.0,
    }
    if confidence is not None:
        metrics["confidence"] = confidence
    if confidence_percentage is not None:
        metrics["confidence_percentage"] = confidence_percentage

    return {
        "id": "x",
        "name": "x",
        "cost": 725.0,
        "dist": {"q10": 600.0, "q50": q50, "q90": 800.0},
        "metrics": metrics,
    }


def _sell_prob() -> dict:
    return {
        "p_sell": 0.65,
        "horizon_days": 7,
        "median_days_to_sell": 18.0,
        "adjusted_days_to_sell": 17.2,
        "pricing_ratio": 1.0,
        "live_price": 725.0,
        "q50_comp_price": 700.0,
        "num_valid_time_comps": 2,
        "num_sold_comps": 3,
    }


def test_run_search_drops_no_data_rows(monkeypatch):
    scrape_result = _scrape_result(["a", "b"])

    async def _scrape_stub(params, persist):
        return scrape_result

    def _value_stub(row_dict, scraped_at):
        if row_dict["live_listing"]["id"] == "a":
            return {"status": "no_data"}
        return _valuation(25.0)

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(orchestrator, "value_listing", _value_stub)
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    response = asyncio.run(orchestrator.run_search(SearchParams(query="guidi")))

    assert [item.live_listing.id for item in response.items] == ["b"]


def test_run_search_sorts_by_edge_usd_desc(monkeypatch):
    scrape_result = _scrape_result(["a", "b", "c"])
    edge_by_id = {"a": 5.0, "b": 50.0, "c": 20.0}

    async def _scrape_stub(params, persist):
        return scrape_result

    def _value_stub(row_dict, scraped_at):
        return _valuation(edge_by_id[row_dict["live_listing"]["id"]])

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(orchestrator, "value_listing", _value_stub)
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    response = asyncio.run(orchestrator.run_search(SearchParams(query="guidi")))

    assert [item.live_listing.id for item in response.items] == ["b", "c", "a"]


class _FakeRecsStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def save_recommendations(self, *, response, params) -> None:
        self.calls.append({"response": response, "params": params})


def test_run_search_persists_recommendations_when_store_set(monkeypatch):
    scrape_result = _scrape_result(["a", "b"])

    async def _scrape_stub(params, persist):
        return scrape_result

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(orchestrator, "value_listing", lambda row, scraped_at: _valuation(10.0))
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    fake = _FakeRecsStore()
    store_mod.set_recommendations_store(fake)
    try:
        params = SearchParams(query="guidi")
        response = asyncio.run(orchestrator.run_search(params))
    finally:
        store_mod.set_recommendations_store(None)

    assert len(fake.calls) == 1
    assert fake.calls[0]["params"] is params
    assert fake.calls[0]["response"] is response


def test_run_search_skips_persist_when_persist_false(monkeypatch):
    scrape_result = _scrape_result(["a"])

    async def _scrape_stub(params, persist):
        return scrape_result

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(orchestrator, "value_listing", lambda row, scraped_at: _valuation(10.0))
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    fake = _FakeRecsStore()
    store_mod.set_recommendations_store(fake)
    try:
        asyncio.run(orchestrator.run_search(SearchParams(query="guidi"), persist=False))
    finally:
        store_mod.set_recommendations_store(None)

    assert fake.calls == []


def test_run_search_no_crash_when_store_unset(monkeypatch):
    scrape_result = _scrape_result(["a"])

    async def _scrape_stub(params, persist):
        return scrape_result

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(orchestrator, "value_listing", lambda row, scraped_at: _valuation(10.0))
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    store_mod.set_recommendations_store(None)
    response = asyncio.run(orchestrator.run_search(SearchParams(query="guidi")))

    assert len(response.items) == 1


def test_run_search_propagates_persist_flag_to_scraper(monkeypatch):
    calls: list[bool] = []

    async def _scrape_stub(params, persist):
        calls.append(persist)
        return _scrape_result([])

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(orchestrator, "value_listing", lambda row, scraped_at: _valuation(1.0))
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    asyncio.run(orchestrator.run_search(SearchParams(query="guidi"), persist=False))
    asyncio.run(orchestrator.run_search(SearchParams(query="guidi"), persist=True))

    assert calls == [False, True]


def test_run_search_returns_empty_ranked_when_all_no_data(monkeypatch):
    scrape_result = _scrape_result(["a", "b"])

    async def _scrape_stub(params, persist):
        return scrape_result

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(orchestrator, "value_listing", lambda row, scraped_at: {"status": "no_data"})
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    response = asyncio.run(orchestrator.run_search(SearchParams(query="guidi")))

    assert response.items == []
    assert response.metadata.scraped_at_unix == scrape_result.metadata.scraped_at_unix


def test_run_search_derives_confidence_from_percentage(monkeypatch):
    scrape_result = _scrape_result(["a"])

    async def _scrape_stub(params, persist):
        return scrape_result

    monkeypatch.setattr(orchestrator, "scrape", _scrape_stub)
    monkeypatch.setattr(
        orchestrator,
        "value_listing",
        lambda row, scraped_at: _valuation(10.0, confidence=None, confidence_percentage=62.0),
    )
    monkeypatch.setattr(orchestrator, "estimate_sell_probability", lambda row: _sell_prob())

    response = asyncio.run(orchestrator.run_search(SearchParams(query="guidi")))

    assert len(response.items) == 1
    assert response.items[0].confidence == "medium"


def test_run_hype_calls_each_fetch_once_and_assembles_result(monkeypatch):
    calls: list[tuple[str, str]] = []
    related_calls: list[str] = []
    compute_args: list[list[TrendPoint]] = []

    series_30 = TrendSeries(
        range="30d",
        points=[TrendPoint(day_unix=1700000000, intensity=10), TrendPoint(day_unix=1700086400, intensity=20)],
    )
    series_7 = TrendSeries(range="7d", points=[TrendPoint(day_unix=1700000000, intensity=11)])
    series_90 = TrendSeries(range="90d", points=[TrendPoint(day_unix=1700000000, intensity=12)])
    related_items = [RelatedQuery(query="guidi 788z", value=45, kind="top", is_breakout=False)]

    def _trends_fetch(term: str, range_value: str):
        calls.append((term, range_value))
        if range_value == "30d":
            return series_30
        if range_value == "7d":
            return series_7
        return series_90

    def _related_fetch(term: str):
        related_calls.append(term)
        return related_items

    def _compute(points: list[TrendPoint]):
        compute_args.append(points)
        return 1.25, "high"

    monkeypatch.setattr(orchestrator.trends, "fetch", _trends_fetch)
    monkeypatch.setattr(orchestrator.related, "fetch", _related_fetch)
    monkeypatch.setattr(orchestrator.score, "compute", _compute)

    before = int(datetime.now(tz=UTC).timestamp())
    result = asyncio.run(orchestrator.run_hype("guidi"))
    after = int(datetime.now(tz=UTC).timestamp())

    assert sorted(calls) == sorted([("guidi", "30d"), ("guidi", "7d"), ("guidi", "90d")])
    assert related_calls == ["guidi"]
    assert compute_args == [series_30.points]
    assert result.term == "guidi"
    assert result.score == 1.25
    assert result.confidence == "high"
    assert result.series_30d == series_30
    assert result.series_7d == series_7
    assert result.series_90d == series_90
    assert result.evidence == HypeEvidence(related=related_items)
    assert before <= result.fetched_at_unix <= after