"""Smoke tests for the FastAPI handlers in backend/main.py.

The orchestrator and store are stubbed; these tests only verify wiring,
auth, validation, and response shape. Real I/O lives in scraper / EV / hype
unit tests and the manual integration check in the design doc.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend import main as main_mod
from shared.models import (
    HypeEvidence,
    HypeResult,
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchParams,
    SearchResponse,
    Seller,
    SellerBadges,
    TrendPoint,
    TrendSeries,
)


class _FakeSupabase:
    """No-op stand-in for ``supabase.Client`` so lifespan can construct a store."""


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-key")
    monkeypatch.setenv("SUPABASE_URL", "http://localhost")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.setattr(main_mod, "API_KEY", "test-key")
    monkeypatch.setattr(main_mod, "create_client", lambda url, key: _FakeSupabase())

    with TestClient(main_mod.app) as c:
        yield c


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


def _search_response(item_id: str = "a") -> SearchResponse:
    metadata = ScrapeMetadata(
        query="guidi",
        categories=["menswear"],
        live_limit_requested=3,
        sold_limit_requested=5,
        scraped_at_unix=1700000000,
        total_live_found=1,
    )
    rec = Recommendation(
        item_id=item_id,
        scraped_at_unix=1700000000,
        query="guidi",
        edge_usd=50.0,
        p_sell=0.5,
        q50=700.0,
        cost=725.0,
        confidence="medium",
        valuation={
            "id": item_id,
            "name": "Boot",
            "cost": 725.0,
            "dist": {"q10": 600.0, "q50": 700.0, "q90": 800.0},
            "metrics": {
                "edge_usd": 50.0,
                "percent_under": 7.0,
                "effective_n": 3.0,
                "confidence": "medium",
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
        live_listing=_live(item_id),
    )
    return SearchResponse(metadata=metadata, items=[rec])


def _hype_result(term: str) -> HypeResult:
    return HypeResult(
        term=term,
        score=0.42,
        confidence="medium",
        series_30d=TrendSeries(
            range="30d", points=[TrendPoint(day_unix=1700000000, intensity=10)]
        ),
        series_7d=TrendSeries(
            range="7d", points=[TrendPoint(day_unix=1700000000, intensity=11)]
        ),
        series_90d=TrendSeries(
            range="90d", points=[TrendPoint(day_unix=1700000000, intensity=12)]
        ),
        evidence=HypeEvidence(related=[]),
        fetched_at_unix=1700000999,
    )


def _rec_row(item_id: str, edge_usd: float) -> dict[str, Any]:
    return {
        "item_id": item_id,
        "scraped_at_unix": 1700000000,
        "query": "guidi",
        "edge_usd": edge_usd,
        "p_sell": 0.5,
        "q50": 700.0,
        "cost": 725.0,
        "confidence": "medium",
        "valuation": {
            "id": item_id,
            "name": "Boot",
            "cost": 725.0,
            "dist": {"q10": 600.0, "q50": 700.0, "q90": 800.0},
            "metrics": {
                "edge_usd": edge_usd,
                "percent_under": 7.0,
                "effective_n": 3.0,
                "confidence": "medium",
            },
        },
        "sell_probability": {
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
        "live_listing": _live(item_id).model_dump(mode="json"),
    }


def test_health_does_not_require_bearer(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json() == {"status": "ok"}


def test_search_requires_bearer(client):
    res = client.post("/search", json={"query": "guidi"})
    assert res.status_code == 401


def test_hype_requires_bearer(client):
    res = client.get("/hype/guidi")
    assert res.status_code == 401


def test_recommendations_requires_bearer(client):
    res = client.get("/recommendations")
    assert res.status_code == 401


def test_search_handler_invokes_orchestrator(client, monkeypatch):
    calls: list[SearchParams] = []

    async def _stub(params: SearchParams) -> SearchResponse:
        calls.append(params)
        return _search_response()

    monkeypatch.setattr(main_mod, "run_search", _stub)

    res = client.post(
        "/search",
        headers={"Authorization": "Bearer test-key"},
        json={"query": "guidi", "live_limit": 3, "sold_limit": 5},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["metadata"]["query"] == "guidi"
    assert len(body["items"]) == 1
    assert body["items"][0]["live_listing"]["id"] == "a"
    assert body["items"][0]["item_id"] == "a"
    assert body["items"][0]["edge_usd"] == 50.0

    assert len(calls) == 1
    assert calls[0].query == "guidi"
    assert calls[0].live_limit == 3
    assert calls[0].sold_limit == 5


def test_hype_handler_invokes_orchestrator(client, monkeypatch):
    calls: list[str] = []

    async def _stub(term: str) -> HypeResult:
        calls.append(term)
        return _hype_result(term)

    monkeypatch.setattr(main_mod, "run_hype", _stub)

    res = client.get("/hype/guidi", headers={"Authorization": "Bearer test-key"})

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["term"] == "guidi"
    assert body["confidence"] == "medium"
    assert calls == ["guidi"]


def test_hype_handler_url_decodes_term(client, monkeypatch):
    calls: list[str] = []

    async def _stub(term: str) -> HypeResult:
        calls.append(term)
        return _hype_result(term)

    monkeypatch.setattr(main_mod, "run_hype", _stub)

    res = client.get(
        "/hype/comme%20des%20gar%C3%A7ons",
        headers={"Authorization": "Bearer test-key"},
    )

    assert res.status_code == 200, res.text
    assert calls == ["comme des garçons"]


def test_recommendations_handler_returns_items_sorted(client, monkeypatch):
    rows = [_rec_row("low", 5.0), _rec_row("high", 99.0), _rec_row("mid", 25.0)]

    class _Store:
        def list_recommendations(self, *, limit: int):
            return rows

    monkeypatch.setattr(main_mod, "get_recommendations_store", lambda: _Store())

    res = client.get(
        "/recommendations?limit=10",
        headers={"Authorization": "Bearer test-key"},
    )

    assert res.status_code == 200, res.text
    items = res.json()["items"]
    assert [i["item_id"] for i in items] == ["high", "mid", "low"]
    assert items[0]["valuation"]["metrics"]["edge_usd"] == 99.0
    assert items[0]["live_listing"]["id"] == "high"


def test_recommendations_handler_returns_empty_when_no_store(client, monkeypatch):
    monkeypatch.setattr(main_mod, "get_recommendations_store", lambda: None)

    res = client.get(
        "/recommendations",
        headers={"Authorization": "Bearer test-key"},
    )

    assert res.status_code == 200
    assert res.json() == {"items": []}


def test_recommendations_handler_rejects_limit_zero(client):
    res = client.get(
        "/recommendations?limit=0",
        headers={"Authorization": "Bearer test-key"},
    )
    assert res.status_code == 422


def test_recommendations_handler_rejects_limit_too_large(client):
    res = client.get(
        "/recommendations?limit=999",
        headers={"Authorization": "Bearer test-key"},
    )
    assert res.status_code == 422


def test_agent_run_stream_requires_bearer(client):
    res = client.post("/agent/run", json={"intent_text": "find ccp"})
    assert res.status_code == 401


def test_agent_run_stream_returns_sse(client, monkeypatch):
    async def _stub(*, intent_text: str, seed_params=None):
        yield {"type": "intent_parsed", "params": {"query": "ccp"}, "reasoning": "stub"}
        yield {"type": "done", "total_duration_ms": 1, "queries_run": 0, "queries_failed": 0, "total_items": 0}

    monkeypatch.setattr(main_mod, "run_agent_stream", _stub)

    with client.stream(
        "POST",
        "/agent/run",
        headers={"Authorization": "Bearer test-key"},
        json={"intent_text": "find ccp"},
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = "".join(chunk for chunk in response.iter_text())
    assert '"type": "intent_parsed"' in body
    assert '"type": "done"' in body
