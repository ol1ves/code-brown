"""Single concrete listing persistence. Supabase-backed today; swap instance at app boot."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from supabase import Client

if TYPE_CHECKING:
    from shared.models import SearchParams, SearchResponse


class ListingStore:
    """Wraps DB access for scraper + EV. No supabase imports outside this module.

    ``save_listing`` expects a dict shaped like ``LiveListing.model_dump()`` with an
    extra top-level ``category`` string (from scrape metadata / filters).
    """

    _TABLE = "listings"
    _RECS_TABLE = "recommendations"

    def __init__(self, db: Client) -> None:
        self._db = db

    def save_listing(self, listing: dict) -> None:
        row = {
            "item_id": listing["id"],
            "category": listing["category"],
            "payload": listing,
        }
        self._db.table(self._TABLE).upsert(row, on_conflict="item_id").execute()

    def get_listing(self, item_id: str) -> dict | None:
        res = (
            self._db.table(self._TABLE)
            .select("payload")
            .eq("item_id", item_id)
            .limit(1)
            .execute()
        )
        return res.data[0]["payload"] if res.data else None

    def has_listing(self, item_id: str) -> bool:
        res = (
            self._db.table(self._TABLE)
            .select("item_id")
            .eq("item_id", item_id)
            .limit(1)
            .execute()
        )
        return bool(res.data)

    def list_recent(self, category: str, since: datetime) -> list[dict]:
        res = (
            self._db.table(self._TABLE)
            .select("payload")
            .eq("category", category)
            .gte("created_at", since.isoformat())
            .order("created_at", desc=True)
            .execute()
        )
        return [r["payload"] for r in (res.data or [])]

    def save_recommendations(
        self,
        *,
        response: "SearchResponse",
        params: "SearchParams",
    ) -> None:
        """Bulk-insert one row per Recommendation. No-op if response.items is empty."""
        if not response.items:
            return
        params_json = params.model_dump(mode="json")
        rows = [
            {
                "item_id": item.item_id,
                "scraped_at_unix": item.scraped_at_unix,
                "query": item.query,
                "params": params_json,
                "edge_usd": item.edge_usd,
                "p_sell": item.p_sell,
                "q50": item.q50,
                "cost": item.cost,
                "confidence": item.confidence,
                "valuation": item.valuation,
                "sell_probability": item.sell_probability,
                "live_listing": item.live_listing.model_dump(mode="json"),
            }
            for item in response.items
        ]
        self._db.table(self._RECS_TABLE).insert(rows).execute()

    def list_recommendations(self, *, limit: int = 50) -> list[dict]:
        """Latest row per ``item_id``, ordered by ``edge_usd`` desc.

        PostgREST does not expose ``DISTINCT ON``; the ordering and dedupe live
        in the ``list_latest_recommendations`` SQL function shipped alongside
        the table migration.
        """
        res = self._db.rpc(
            "list_latest_recommendations",
            {"p_limit": limit},
        ).execute()
        return res.data or []


_recommendations_store: ListingStore | None = None


def set_recommendations_store(store: ListingStore | None) -> None:
    """Wire (or unwire) the global ListingStore used to persist ranked recommendations."""
    global _recommendations_store
    _recommendations_store = store


def get_recommendations_store() -> ListingStore | None:
    return _recommendations_store
