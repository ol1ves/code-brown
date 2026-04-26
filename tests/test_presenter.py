from __future__ import annotations

from backend.pipeline.context import RunContext
from backend.presenter import render_search_result
from shared.models import (
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchResponse,
    Seller,
    SellerBadges,
)


def _seller() -> Seller:
    return Seller(
        seller_name="tester",
        reviews_count=1,
        transactions_count=1,
        items_for_sale_count=1,
        posted_at_unix=1700000000,
        badges=SellerBadges(
            verified=True,
            trusted_seller=False,
            quick_responder=False,
            speedy_shipper=False,
        ),
    )


def _live(item_id: str) -> LiveListing:
    return LiveListing(
        id=item_id,
        url=f"https://www.grailed.com/listings/{item_id}",
        designer="Guidi",
        name=f"Boot {item_id}",
        size="43",
        condition_raw="Used",
        location="US",
        color="Black",
        image_urls=[],
        price=LivePrice(listing_price_usd=700, shipping_price_usd=25),
        seller=_seller(),
        description="desc",
    )


def _rec(item_id: str, profit: float = 50.0) -> Recommendation:
    return Recommendation(
        item_id=item_id,
        scraped_at_unix=1700000000,
        query="guidi",
        expected_profit_grailed=profit,
        expected_profit_off_grailed=profit + 20.0,
        buy_cost=700.0,
        p_sell=0.5,
        q50=820.0,
        confidence_pct=70.0,
        valuation={"metrics": {"num_valid_time_comps": 2, "num_valid_price_comps": 3}},
        sell_probability={"p_sell": 0.5},
        live_listing=_live(item_id),
    )


def _response(items: list[Recommendation]) -> SearchResponse:
    return SearchResponse(
        metadata=ScrapeMetadata(
            query="guidi",
            categories=["menswear"],
            live_limit_requested=10,
            sold_limit_requested=10,
            scraped_at_unix=1700000000,
            total_live_found=len(items),
        ),
        items=items,
    )


def test_render_includes_all_three_sections():
    ctx = RunContext()
    ctx.timings_ms = {"scrape": 100, "value": 20, "rank": 1, "persist": 5}
    ctx.counts = {"scrape.live_returned": 1, "value.valued": 1, "rank.ranked": 1}
    out = render_search_result(_response([_rec("a")]), ctx, use_color=False)
    assert "STAGE TIMINGS" in out
    assert "TOP" in out
    assert "WARNINGS" in out


def test_render_truncates_warnings_section():
    ctx = RunContext()
    ctx.timings_ms = {"scrape": 100}
    ctx.warnings = [f"w{i}" for i in range(20)]
    out = render_search_result(_response([_rec("a")]), ctx, use_color=False)
    assert "(14 more" in out


def test_render_no_color_when_disabled():
    ctx = RunContext()
    ctx.timings_ms = {"scrape": 100}
    out = render_search_result(_response([_rec("a")]), ctx, use_color=False)
    assert "\x1b[" not in out


def test_render_top_n_caps_at_arg():
    ctx = RunContext()
    ctx.timings_ms = {"scrape": 100}
    items = [_rec(f"id-{i}", profit=float(i)) for i in range(50)]
    out = render_search_result(_response(items), ctx, top_n=20, use_color=False)
    result_lines = [line for line in out.splitlines() if line.strip().startswith(tuple(str(i) for i in range(1, 21)))]
    assert len(result_lines) == 20
