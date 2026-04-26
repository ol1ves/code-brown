"""Unit tests for ListingStore.save_recommendations / list_recommendations."""

from __future__ import annotations

from typing import Any

from shared.models import (
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchParams,
    SearchResponse,
    Seller,
    SellerBadges,
)
from shared.store import ListingStore


class _ExecResult:
    def __init__(self, data: Any = None) -> None:
        self.data = data


class _RpcCall:
    def __init__(self, recorder: list, data: Any) -> None:
        self._recorder = recorder
        self._data = data

    def execute(self) -> _ExecResult:
        return _ExecResult(self._data)


class _InsertCall:
    def __init__(self, recorder: list, payload: Any) -> None:
        self._recorder = recorder
        self._payload = payload

    def execute(self) -> _ExecResult:
        self._recorder.append(self._payload)
        return _ExecResult([])


class _Table:
    def __init__(self, name: str, recorder: dict) -> None:
        self._name = name
        self._recorder = recorder

    def insert(self, payload: Any) -> _InsertCall:
        return _InsertCall(self._recorder.setdefault(self._name, []), payload)


class FakeSupabase:
    """Minimal stand-in for ``supabase.Client`` covering the calls store uses."""

    def __init__(self, rpc_data: Any | None = None) -> None:
        self.inserts: dict[str, list] = {}
        self.rpc_calls: list[tuple[str, dict]] = []
        self._rpc_data = rpc_data

    def table(self, name: str) -> _Table:
        return _Table(name, self.inserts)

    def rpc(self, fn_name: str, params: dict) -> _RpcCall:
        self.rpc_calls.append((fn_name, params))
        return _RpcCall(self.rpc_calls, self._rpc_data)


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


def _valuation(expected_profit_grailed: float, q50: float, buy_cost: float, confidence_pct: float) -> dict:
    return {
        "id": "x",
        "name": "x",
        "buy_cost": buy_cost,
        "dist": {"q10": q50 - 100, "q50": q50, "q90": q50 + 100},
        "metrics": {
            "edge_usd": q50 - buy_cost,
            "expected_profit_grailed": expected_profit_grailed,
            "expected_profit_off_grailed": expected_profit_grailed + 30.0,
            "percent_under": 0.0,
            "effective_n": 4.0,
            "confidence_percentage": confidence_pct,
        },
        "extra_future_field": "ignored-by-store-but-survives-as-jsonb",
    }


def _sell_prob(p_sell: float) -> dict:
    return {
        "p_sell": p_sell,
        "horizon_days": 7,
        "median_days_to_sell": 18.0,
        "adjusted_days_to_sell": 17.2,
        "pricing_ratio": 1.0,
        "live_price": 725.0,
        "q50_comp_price": 700.0,
        "num_valid_time_comps": 2,
        "num_sold_comps": 3,
        "extra_future_field": 1.23,
    }


def _ranked(item_id: str, expected_profit_grailed: float, p_sell: float, confidence_pct: float = 55.0,
            scraped_at_unix: int = 1700000999) -> Recommendation:
    return Recommendation(
        item_id=item_id,
        scraped_at_unix=scraped_at_unix,
        query="guidi",
        expected_profit_grailed=expected_profit_grailed,
        expected_profit_off_grailed=expected_profit_grailed + 30.0,
        buy_cost=725.0,
        p_sell=p_sell,
        q50=700.0,
        confidence_pct=confidence_pct,
        valuation=_valuation(
            expected_profit_grailed=expected_profit_grailed,
            q50=700.0,
            buy_cost=725.0,
            confidence_pct=confidence_pct,
        ),
        sell_probability=_sell_prob(p_sell),
        live_listing=_live(item_id),
    )


def _response(items: list[Recommendation], scraped_at_unix: int = 1700000999) -> SearchResponse:
    metadata = ScrapeMetadata(
        query="guidi",
        categories=["menswear"],
        live_limit_requested=5,
        sold_limit_requested=3,
        scraped_at_unix=scraped_at_unix,
        total_live_found=len(items),
    )
    return SearchResponse(metadata=metadata, items=items)


def test_save_recommendations_inserts_one_row_per_ranked_item():
    fake = FakeSupabase()
    store = ListingStore(fake)
    response = _response(
        [
            _ranked("a", 10.0, 0.5),
            _ranked("b", 25.0, 0.4),
            _ranked("c", 5.0, 0.6),
        ]
    )

    store.save_recommendations(response=response, params=SearchParams(query="guidi"))

    assert "recommendations" in fake.inserts
    payloads = fake.inserts["recommendations"]
    assert len(payloads) == 1
    rows = payloads[0]
    assert isinstance(rows, list)
    assert [r["item_id"] for r in rows] == ["a", "b", "c"]
    for row in rows:
        assert set(row.keys()) == {
            "item_id",
            "scraped_at_unix",
            "query",
            "params",
            "expected_profit_grailed",
            "expected_profit_off_grailed",
            "buy_cost",
            "p_sell",
            "q50",
            "confidence_pct",
            "valuation",
            "sell_probability",
            "live_listing",
        }


def test_save_recommendations_noop_on_empty_ranked():
    fake = FakeSupabase()
    store = ListingStore(fake)
    response = _response([])

    store.save_recommendations(response=response, params=SearchParams(query="guidi"))

    assert fake.inserts == {}


def test_save_recommendations_extracts_typed_columns_correctly():
    fake = FakeSupabase()
    store = ListingStore(fake)
    response = _response([_ranked("a", expected_profit_grailed=42.0, p_sell=0.73, confidence_pct=88.0)])

    store.save_recommendations(response=response, params=SearchParams(query="guidi"))

    row = fake.inserts["recommendations"][0][0]
    assert row["item_id"] == "a"
    assert row["scraped_at_unix"] == 1700000999
    assert row["query"] == "guidi"
    assert row["expected_profit_grailed"] == 42.0
    assert row["expected_profit_off_grailed"] == 72.0
    assert row["buy_cost"] == 725.0
    assert row["p_sell"] == 0.73
    assert row["q50"] == 700.0
    assert row["confidence_pct"] == 88.0
    assert row["valuation"]["extra_future_field"] == "ignored-by-store-but-survives-as-jsonb"
    assert row["sell_probability"]["extra_future_field"] == 1.23
    assert row["live_listing"]["id"] == "a"
    assert row["live_listing"]["designer"] == "Guidi"


def test_save_recommendations_passes_params_as_jsonb():
    fake = FakeSupabase()
    store = ListingStore(fake)
    params = SearchParams(query="guidi", department="menswear", live_limit=7, sold_limit=4)
    response = _response([_ranked("a", 10.0, 0.5)])

    store.save_recommendations(response=response, params=params)

    row = fake.inserts["recommendations"][0][0]
    assert row["params"] == params.model_dump(mode="json")


def test_list_recommendations_calls_rpc_and_returns_data():
    fake = FakeSupabase(rpc_data=[{"item_id": "a"}, {"item_id": "b"}])
    store = ListingStore(fake)

    rows = store.list_recommendations(limit=25)

    assert rows == [{"item_id": "a"}, {"item_id": "b"}]
    assert fake.rpc_calls[0][0] == "list_latest_recommendations"
    assert fake.rpc_calls[0][1] == {"p_limit": 25}


def test_list_recommendations_returns_empty_list_when_rpc_data_none():
    fake = FakeSupabase(rpc_data=None)
    store = ListingStore(fake)

    assert store.list_recommendations() == []
