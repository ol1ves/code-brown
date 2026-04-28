"""Tweet dataclass tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from xscraper.models import Tweet


def _sample() -> Tweet:
    return Tweet(
        id="1234567890",
        text="hello world",
        created_at=1714056731,
        handle="testuser",
        lang="en",
        like_count=42,
        retweet_count=7,
        reply_count=3,
        quote_count=1,
    )


def test_fields_set_correctly():
    t = _sample()
    assert t.id == "1234567890"
    assert t.text == "hello world"
    assert t.created_at == 1714056731
    assert t.handle == "testuser"
    assert t.lang == "en"
    assert t.like_count == 42
    assert t.retweet_count == 7
    assert t.reply_count == 3
    assert t.quote_count == 1


def test_is_frozen():
    t = _sample()
    with pytest.raises(FrozenInstanceError):
        t.text = "mutated"  # type: ignore[misc]


def test_asdict_roundtrip():
    t = _sample()
    d = asdict(t)
    assert d["id"] == "1234567890"
    assert d["like_count"] == 42
