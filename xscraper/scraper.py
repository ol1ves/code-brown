"""Search orchestrator for xscraper.

Loads config, opens an XClient, builds a SearchTimeline request, parses the
response into Tweets, and returns up to ``limit`` of them. Single GraphQL
request per call — no pagination.
"""

from __future__ import annotations

import logging
import time

from xscraper.client import XClient
from xscraper.config import load_config
from xscraper.graphql import build_search_request, parse_search_response
from xscraper.models import Tweet

_log = logging.getLogger("xscraper.scraper")


async def search(query: str, limit: int) -> list[Tweet]:
    """Search X Latest for ``query``, return at most ``limit`` tweets."""
    started_at = time.monotonic()
    _log.info("search start", extra={"query": query, "limit": limit})
    tweets = await _run_search(query, limit)
    truncated = tweets[:limit]
    elapsed_ms = int((time.monotonic() - started_at) * 1000)
    _log.info(
        "search done",
        extra={"count": len(truncated), "elapsed_ms": elapsed_ms},
    )
    return truncated


async def _run_search(query: str, limit: int) -> list[Tweet]:
    """Live path; isolated so tests can monkeypatch it without touching httpx."""
    cfg = load_config()
    url, params = build_search_request(query, limit)
    async with XClient(cfg) as client:
        raw = await client.get_graphql(url, params)
    return parse_search_response(raw)
