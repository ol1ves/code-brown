from __future__ import annotations
import json

from backend import cli
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


def _search_response() -> SearchResponse:
    live = LiveListing(
        id="1",
        url="https://www.grailed.com/listings/1",
        designer="Guidi",
        name="788Z",
        size="43",
        condition_raw="Used",
        location="US",
        color="Black",
        image_urls=[],
        price=LivePrice(listing_price_usd=700, shipping_price_usd=25),
        seller=_seller(),
        description="desc",
    )
    rec = Recommendation(
        item_id="1",
        scraped_at_unix=1700000000,
        query="guidi",
        expected_profit_grailed=55.0,
        expected_profit_off_grailed=70.0,
        buy_cost=725.0,
        p_sell=0.5,
        q50=700.0,
        confidence_pct=62.0,
        valuation={
            "id": "1",
            "name": "788Z",
            "buy_cost": 725.0,
            "dist": {"q10": 610.0, "q50": 700.0, "q90": 780.0},
            "metrics": {
                "edge_usd": 55.0,
                "expected_profit_grailed": 55.0,
                "expected_profit_off_grailed": 70.0,
                "percent_under": 7.59,
                "effective_n": 3.0,
                "confidence_percentage": 62.0,
            },
        },
        sell_probability={
            "p_sell": 0.5,
            "horizon_days": 7,
            "median_days_to_sell": 10.0,
            "adjusted_days_to_sell": 11.0,
            "pricing_ratio": 1.0,
            "live_price": 725.0,
            "q50_comp_price": 700.0,
            "num_valid_time_comps": 2,
            "num_sold_comps": 3,
        },
        live_listing=live,
    )
    metadata = ScrapeMetadata(
        query="guidi",
        categories=["menswear"],
        live_limit_requested=3,
        sold_limit_requested=5,
        scraped_at_unix=1700000000,
        total_live_found=1,
    )
    return SearchResponse(metadata=metadata, items=[rec])


def test_search_subcommand_invokes_run_search(monkeypatch, capsys):
    calls: list[tuple[str, int, int, bool]] = []

    async def _run_search_stub(params, ctx, *, persist: bool = True):
        calls.append((params.query, params.live_limit, params.sold_limit, persist))
        return _search_response()

    monkeypatch.setattr(cli, "run_search", _run_search_stub)
    monkeypatch.setattr(cli, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli, "_wire_stores", lambda: None)

    exit_code = cli.main(["search", "margiela gats", "40", "40"])

    out = capsys.readouterr().out
    assert exit_code == 0
    assert len(calls) == 1
    assert calls[0] == ("margiela gats", 40, 40, True)
    assert "TOP 20 RESULTS" in out


def test_search_subcommand_json_flag_produces_valid_json(monkeypatch, capsys):
    async def _run_search_stub(params, ctx, *, persist: bool = True):
        return _search_response()

    monkeypatch.setattr(cli, "run_search", _run_search_stub)
    monkeypatch.setattr(cli, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli, "_wire_stores", lambda: None)

    exit_code = cli.main(["search", "guidi", "20", "30", "--no-persist", "--json"])

    out = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(out)
    assert "metadata" in payload
    assert "items" in payload


def test_search_subcommand_no_persist_skips_store_wiring(monkeypatch):
    called = {"wire": 0}

    async def _run_search_stub(params, ctx, *, persist: bool = True):
        return _search_response()

    monkeypatch.setattr(cli, "run_search", _run_search_stub)
    monkeypatch.setattr(cli, "configure_logging", lambda **kwargs: None)
    monkeypatch.setattr(cli, "_wire_stores", lambda: called.__setitem__("wire", called["wire"] + 1))

    exit_code = cli.main(["search", "guidi", "20", "30", "--no-persist"])
    assert exit_code == 0
    assert called["wire"] == 0