"""SearchTimeline parser tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from xscraper.exceptions import XSchemaError
from xscraper.graphql import parse_search_response

def test_parse_returns_one_tweet(load_fixture):
    raw = load_fixture("search_latest.json")
    tweets = parse_search_response(raw)
    assert len(tweets) == 1

def test_tweet_fields_populated(load_fixture):
    raw = load_fixture("search_latest.json")
    [t] = parse_search_response(raw)
    assert t.id == "1234567890123456789"
    assert t.text == "hello world"
    assert t.handle == "testuser"
    assert t.lang == "en"
    assert t.like_count == 42
    assert t.retweet_count == 7
    assert t.reply_count == 3
    assert t.quote_count == 1
    expected = int(
        datetime(2026, 4, 23, 14, 32, 11, tzinfo=timezone.utc).timestamp()
    )
    assert t.created_at == expected

def test_cursor_entries_skipped(load_fixture):
    # Fixture has one cursor- entry; final list size confirms it was skipped.
    raw = load_fixture("search_latest.json")
    tweets = parse_search_response(raw)
    handles = {t.handle for t in tweets}
    assert handles == {"testuser"}

def test_empty_response_raises_schema_error():
    with pytest.raises(XSchemaError):
        parse_search_response({})

def test_missing_instructions_raises_schema_error():
    bad = {"data": {"search_by_raw_query": {"search_timeline": {"timeline": {}}}}}
    with pytest.raises(XSchemaError):
        parse_search_response(bad)

def test_no_tweet_entries_raises_schema_error():
    """An empty entries list is indistinguishable from a broken parser; raise."""
    bad = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {"type": "TimelineAddEntries", "entries": []}
                        ]
                    }
                }
            }
        }
    }
    with pytest.raises(XSchemaError):
        parse_search_response(bad)