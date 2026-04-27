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
