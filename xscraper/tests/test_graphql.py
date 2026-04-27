"""GraphQL request builder + response parser unit tests."""

from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

from xscraper.graphql import (
    DOC_ID,
    SEARCH_TIMELINE_OP,
    build_search_request,
)


def test_build_search_request_url_uses_doc_id_and_op():
    url, _params = build_search_request("margiela tabi", limit=10)
    parsed = urlparse(url)
    assert parsed.netloc == "x.com"
    assert parsed.path == f"/i/api/graphql/{DOC_ID}/{SEARCH_TIMELINE_OP}"


def test_build_search_request_variables_carry_query_and_limit():
    _url, params = build_search_request("margiela tabi", limit=10)
    variables = json.loads(params["variables"])
    assert variables["rawQuery"] == "margiela tabi"
    assert variables["count"] == 10
    assert variables["product"] == "Latest"
    assert variables["querySource"] == "typed_query"


def test_build_search_request_includes_features_dict():
    _url, params = build_search_request("foo", limit=5)
    features = json.loads(params["features"])
    assert isinstance(features, dict)
    assert len(features) > 0  # sanity: non-empty


def test_build_search_request_url_encodes_special_chars():
    """Caller passes raw string; we do not URL-encode the URL path itself
    (variables go in query params, encoded by httpx). The path must remain
    static — no template interpolation of the query."""
    url, _ = build_search_request("a&b=c", limit=3)
    assert "&" not in urlparse(url).path
    assert "=" not in urlparse(url).path


import pytest

from xscraper.exceptions import XSchemaError
from xscraper.graphql import parse_search_response
from xscraper.models import Tweet


def test_parse_search_response_returns_one_tweet(load_fixture):
    raw = load_fixture("search_latest.json")
    tweets = parse_search_response(raw)
    assert len(tweets) == 1
    assert isinstance(tweets[0], Tweet)


def test_parse_search_response_fields(load_fixture):
    from datetime import datetime

    raw = load_fixture("search_latest.json")
    [t] = parse_search_response(raw)
    assert t.id == "1234567890123456789"
    assert t.handle == "testuser"
    assert t.text == "hello world"
    assert t.lang == "en"
    assert t.like_count == 42
    assert t.retweet_count == 7
    assert t.reply_count == 3
    assert t.quote_count == 1
    expected_ts = int(
        datetime.strptime(
            "Wed Apr 23 14:32:11 +0000 2026", "%a %b %d %H:%M:%S %z %Y"
        ).timestamp()
    )
    assert t.created_at == expected_ts


def test_parse_search_response_skips_cursor_entries(load_fixture):
    raw = load_fixture("search_latest.json")
    tweets = parse_search_response(raw)
    # Only the tweet-prefixed entry, never the cursor.
    assert all(t.id == "1234567890123456789" for t in tweets)


def test_parse_search_response_empty_dict_raises():
    with pytest.raises(XSchemaError):
        parse_search_response({})


def test_parse_search_response_missing_instructions_raises():
    bad = {"data": {"search_by_raw_query": {"search_timeline": {"timeline": {}}}}}
    with pytest.raises(XSchemaError):
        parse_search_response(bad)


def test_parse_search_response_no_tweet_entries_raises():
    """Empty success is indistinguishable from broken parser — fail loud."""
    bad = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {"type": "TimelineAddEntries", "entries": [
                                {"entryId": "cursor-top-x", "content": {}}
                            ]}
                        ]
                    }
                }
            }
        }
    }
    with pytest.raises(XSchemaError):
        parse_search_response(bad)
