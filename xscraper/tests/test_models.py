"""Tweet dataclass unit tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from xscraper.models import Tweet


def _sample() -> Tweet:
    return Tweet(
        id="1234567890123456789",
        text="hello world",
        created_at=1714831931,
        handle="testuser",
        lang="en",
        like_count=42,
        retweet_count=7,
        reply_count=3,
        quote_count=1,
    )


def test_construct_and_fields():
    t = _sample()
    assert t.id == "1234567890123456789"
    assert t.handle == "testuser"
    assert t.like_count == 42
    assert t.created_at == 1714831931


def test_frozen():
    t = _sample()
    with pytest.raises(FrozenInstanceError):
        t.like_count = 99  # type: ignore[misc]


def test_asdict_round_trip():
    t = _sample()
    d = asdict(t)
    assert d == {
        "id": "1234567890123456789",
        "text": "hello world",
        "created_at": 1714831931,
        "handle": "testuser",
        "lang": "en",
        "like_count": 42,
        "retweet_count": 7,
        "reply_count": 3,
        "quote_count": 1,
    }
