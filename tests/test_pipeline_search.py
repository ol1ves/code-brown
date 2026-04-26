"""Pipeline stage tests.

Public surface is ``run_search``. Stage helpers stay private.
"""

from __future__ import annotations

import asyncio

from backend.pipeline import search as pipeline_search
from backend.pipeline.context import RunContext
from shared.models import (
    GrailedResultRow,
    GrailedScrapeResult,
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchParams,
    Seller,
    SellerBadges,
    SoldListing,
    SoldPrice,
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


def _row(listing_id: str, *, sold_count: int = 1) -> GrailedResultRow:
    return GrailedResultRow(
        live_listing=_live(listing_id),
        sold_comparables=[_sold(f"{listing_id}-{i}") for i in range(sold_count)],
    )


def _scrape_result(row_specs: list[tuple[str, int]]) -> GrailedScrapeResult:
    return GrailedScrapeResult(
        metadata=ScrapeMetadata(
            query="guidi",
            categories=["menswear"],
            live_limit_requested=10,
            sold_limit_requested=10,
            scraped_at_unix=1700000000,
            total_live_found=len(row_specs),
        ),
        results=[_row(rid, sold_count=sc) for rid, sc in row_specs],
    )


def _valuation_success(*, expected_profit_grailed: float, q50: float = 800.0) -> dict:
    return {
        "id": "x",
        "name": "x",
        "cost": 725.0,
        "buy_cost": 786.21,
        "dist": {"q10": 600.0, "q50": q50, "q90": 900.0},
        "metrics": {
            "edge_usd": q50 - 725.0,
            "expected_profit_grailed": expected_profit_grailed,
            "expected_profit_off_grailed": expected_profit_grailed + 30.0,
            "expected_profit_grailed_pct": expected_profit_grailed / 786.21,
            "expected_profit_off_grailed_pct": (expected_profit_grailed + 30.0) / 786.21,
            "grailed_total_fees": 100.0,
            "grailed_net_payout": q50 - 100.0,
            "effective_n": 4.0,
            "confidence_percentage": 72.5,
            "num_valid_price_comps": 5,
            "num_valid_time_comps": 3,
        },
    }


def _sell_prob() -> dict:
    return {
        "p_sell": 0.55,
        "horizon_days": 7,
        "median_days_to_sell": 18.0,
        "adjusted_days_to_sell": 17.2,
        "pricing_ratio": 1.0,
        "live_price": 725.0,
        "q50_comp_price": 700.0,
        "num_valid_time_comps": 2,
        "num_sold_comps": 3,
    }


def test_value_stage_drops_no_data_rows_and_records_count(monkeypatch):
    scrape = _scrape_result([("a", 2), ("b", 2)])
    ctx = RunContext()

    def _value_listing(row_dict, scraped_at):
        if row_dict["live_listing"]["id"] == "a":
            return {"id": "a", "status": "no_data"}
        return _valuation_success(expected_profit_grailed=120.0)

    monkeypatch.setattr(pipeline_search, "value_listing", _value_listing)
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())

    items = pipeline_search._value_stage(scrape, SearchParams(query="guidi"), ctx)

    assert [i.item_id for i in items] == ["b"]
    assert ctx.counts["value.no_data"] == 1
    assert ctx.counts["value.valued"] == 1
    assert ctx.counts["value.errored"] == 0
    assert ctx.counts["value.sold_comps_total"] == 4
    assert any("no_data: a" in w for w in ctx.warnings)


def test_value_stage_extracts_new_top_level_fields(monkeypatch):
    scrape = _scrape_result([("only", 1)])
    ctx = RunContext()
    monkeypatch.setattr(
        pipeline_search,
        "value_listing",
        lambda row, scraped_at: _valuation_success(expected_profit_grailed=88.0, q50=900.0),
    )
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())

    items = pipeline_search._value_stage(scrape, SearchParams(query="guidi"), ctx)

    assert len(items) == 1
    rec = items[0]
    assert rec.expected_profit_grailed == 88.0
    assert rec.expected_profit_off_grailed == 118.0
    assert rec.buy_cost == 786.21
    assert rec.confidence_pct == 72.5
    assert rec.q50 == 900.0


def test_value_stage_per_row_exception_drops_row_and_counts_errored(monkeypatch):
    scrape = _scrape_result([("a", 1), ("b", 1)])
    ctx = RunContext()

    def _value_listing(row_dict, scraped_at):
        if row_dict["live_listing"]["id"] == "a":
            raise RuntimeError("bad row")
        return _valuation_success(expected_profit_grailed=10.0)

    monkeypatch.setattr(pipeline_search, "value_listing", _value_listing)
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())

    items = pipeline_search._value_stage(scrape, SearchParams(query="guidi"), ctx)

    assert [i.item_id for i in items] == ["b"]
    assert ctx.counts["value.errored"] == 1
    assert ctx.counts["value.valued"] == 1


def test_rank_stage_orders_by_p_sell_times_expected_profit_grailed():
    ctx = RunContext()
    items = [
        Recommendation(
            item_id="lo",
            scraped_at_unix=0,
            query="q",
            expected_profit_grailed=10.0,
            expected_profit_off_grailed=12.0,
            buy_cost=100.0,
            p_sell=0.5,
            q50=110.0,
            confidence_pct=50.0,
            valuation={},
            sell_probability={},
            live_listing=_live("lo"),
        ),
        Recommendation(
            item_id="hi",
            scraped_at_unix=0,
            query="q",
            expected_profit_grailed=200.0,
            expected_profit_off_grailed=220.0,
            buy_cost=300.0,
            p_sell=0.5,
            q50=500.0,
            confidence_pct=70.0,
            valuation={},
            sell_probability={},
            live_listing=_live("hi"),
        ),
        Recommendation(
            item_id="mid",
            scraped_at_unix=0,
            query="q",
            expected_profit_grailed=80.0,
            expected_profit_off_grailed=90.0,
            buy_cost=200.0,
            p_sell=0.9,
            q50=280.0,
            confidence_pct=60.0,
            valuation={},
            sell_probability={},
            live_listing=_live("mid"),
        ),
    ]
    ranked = pipeline_search._rank_stage(items, ctx)
    assert [i.item_id for i in ranked] == ["hi", "mid", "lo"]
    assert ctx.counts["rank.ranked"] == 3


def test_run_search_drops_no_data_rows(monkeypatch):
    scrape = _scrape_result([("a", 2), ("b", 2)])
    ctx = RunContext()

    async def _scrape_stage(params, stage_ctx):
        return scrape

    def _value_listing(row_dict, scraped_at):
        if row_dict["live_listing"]["id"] == "a":
            return {"id": "a", "status": "no_data"}
        return _valuation_success(expected_profit_grailed=100.0)

    monkeypatch.setattr(pipeline_search, "_scrape_stage", _scrape_stage)
    monkeypatch.setattr(pipeline_search, "value_listing", _value_listing)
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())
    monkeypatch.setattr(pipeline_search, "_persist_stage", lambda response, params, ctx: None)

    response = asyncio.run(pipeline_search.run_search(SearchParams(query="guidi"), ctx))
    assert [i.item_id for i in response.items] == ["b"]


def test_run_search_records_stage_timings_and_counts(monkeypatch):
    scrape = _scrape_result([("a", 1), ("b", 1)])
    ctx = RunContext()

    async def _scrape_stage(params, stage_ctx):
        stage_ctx.record_stage("scrape", duration_ms=1, live_requested=2, live_returned=2, total_live_found=2)
        return scrape

    monkeypatch.setattr(pipeline_search, "_scrape_stage", _scrape_stage)
    monkeypatch.setattr(
        pipeline_search,
        "value_listing",
        lambda row_dict, scraped_at: _valuation_success(expected_profit_grailed=42.0),
    )
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())
    monkeypatch.setattr(pipeline_search, "_persist_stage", lambda response, params, ctx: ctx.record_stage("persist", duration_ms=1, inserted=len(response.items)))

    asyncio.run(pipeline_search.run_search(SearchParams(query="guidi"), ctx))

    assert {"scrape", "value", "rank", "persist"} <= set(ctx.timings_ms.keys())
    assert "scrape.live_returned" in ctx.counts
    assert "value.valued" in ctx.counts
    assert "value.no_data" in ctx.counts
    assert "rank.ranked" in ctx.counts


def test_run_search_persist_false_skips_persist_stage(monkeypatch):
    scrape = _scrape_result([("a", 1)])
    ctx = RunContext()
    called = {"persist": 0}

    async def _scrape_stage(params, stage_ctx):
        stage_ctx.record_stage("scrape", duration_ms=1, live_requested=1, live_returned=1, total_live_found=1)
        return scrape

    def _persist_stage(response, params, stage_ctx):
        called["persist"] += 1

    monkeypatch.setattr(pipeline_search, "_scrape_stage", _scrape_stage)
    monkeypatch.setattr(
        pipeline_search,
        "value_listing",
        lambda row_dict, scraped_at: _valuation_success(expected_profit_grailed=42.0),
    )
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())
    monkeypatch.setattr(pipeline_search, "_persist_stage", _persist_stage)

    asyncio.run(pipeline_search.run_search(SearchParams(query="guidi"), ctx, persist=False))

    assert called["persist"] == 0
    assert "persist" not in ctx.timings_ms
