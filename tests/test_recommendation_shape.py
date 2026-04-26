"""Recommendation surface fields after EV reconciliation.

The math owner moved confidence from a categorical string to a numeric
``confidence_percentage``, added ``expected_profit_grailed`` (q50 net of
Grailed fees minus buy_cost), and added ``buy_cost`` (listing + NYC tax +
shipping). The Recommendation surface promotes these instead of the legacy
``edge_usd``/``cost``/``confidence`` triple.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.models import (
    LiveListing,
    LivePrice,
    Recommendation,
    Seller,
    SellerBadges,
)


def _live() -> LiveListing:
    return LiveListing(
        id="abc",
        url="https://www.grailed.com/listings/abc",
        designer="Maison Margiela",
        name="Replica GAT",
        size="42",
        condition_raw="Gently Used",
        location="US",
        color="White",
        image_urls=[],
        price=LivePrice(listing_price_usd=189, shipping_price_usd=15),
        seller=Seller(
            seller_name="tester",
            reviews_count=0,
            transactions_count=0,
            items_for_sale_count=0,
            posted_at_unix=1700000000,
            badges=SellerBadges(
                verified=False,
                trusted_seller=False,
                quick_responder=False,
                speedy_shipper=False,
            ),
        ),
        description="",
    )


def test_recommendation_carries_new_top_level_fields():
    rec = Recommendation(
        item_id="abc",
        scraped_at_unix=1700000000,
        query="margiela gats",
        expected_profit_grailed=122.0,
        expected_profit_off_grailed=153.0,
        buy_cost=189.0,
        p_sell=0.71,
        q50=342.0,
        confidence_pct=78.0,
        valuation={"id": "abc", "metrics": {}},
        sell_probability={"p_sell": 0.71},
        live_listing=_live(),
    )
    assert rec.expected_profit_grailed == 122.0
    assert rec.expected_profit_off_grailed == 153.0
    assert rec.buy_cost == 189.0
    assert rec.confidence_pct == 78.0
    assert rec.q50 == 342.0


def test_recommendation_rejects_legacy_fields():
    """Legacy fields must not accept silently.

    Pydantic by default ignores unknown fields, so explicitly assert they
    are not present as attributes after construction.
    """

    rec = Recommendation(
        item_id="abc",
        scraped_at_unix=1700000000,
        query="margiela gats",
        expected_profit_grailed=10.0,
        expected_profit_off_grailed=12.0,
        buy_cost=100.0,
        p_sell=0.5,
        q50=110.0,
        confidence_pct=50.0,
        valuation={},
        sell_probability={},
        live_listing=_live(),
    )
    assert not hasattr(rec, "edge_usd")
    assert not hasattr(rec, "cost")
    assert not hasattr(rec, "confidence")


def test_recommendation_required_fields_missing_raises():
    with pytest.raises(ValidationError):
        Recommendation(
            item_id="abc",
            scraped_at_unix=1700000000,
            query="x",
            expected_profit_off_grailed=1.0,
            buy_cost=1.0,
            p_sell=0.1,
            q50=1.0,
            confidence_pct=1.0,
            valuation={},
            sell_probability={},
            live_listing=_live(),
        )
