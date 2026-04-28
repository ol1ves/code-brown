"""Search orchestrator. CLI's only entry into the data path."""

from __future__ import annotations

import logging
import time

from xscraper.browser import fetch_search_timeline
from xscraper.config import load_config
from xscraper.graphql import parse_search_response
from xscraper.models import Tweet

log = logging.getLogger("xscraper.scraper")


async def search(query: str, limit: int, *, headed: bool = False) -> list[Tweet]:
    """Run one Latest-tab search and return up to ``limit`` Tweet objects."""
    cfg = load_config()
    log.info("search start query=%r limit=%d", query, limit)
    started = time.monotonic()

    raw = await fetch_search_timeline(
        query, state_path=cfg.state_path, headed=headed
    )
    tweets = parse_search_response(raw)
    sliced = tweets[:limit]

    elapsed_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "search done count=%d elapsed_ms=%d", len(sliced), elapsed_ms
    )
    return sliced
