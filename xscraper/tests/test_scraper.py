"""Search orchestrator unit tests w/ mocked client."""

from __future__ import annotations

import pytest

from xscraper.models import Tweet
from xscraper import scraper as scraper_mod


def _tweet(idx: int) -> Tweet:
    return Tweet(
        id=str(idx),
        text=f"tweet {idx}",
        created_at=1714831931 + idx,
        handle=f"u{idx}",
        lang="en",
        like_count=idx,
        retweet_count=0,
        reply_count=0,
        quote_count=0,
    )


@pytest.mark.asyncio
async def test_search_returns_parsed_tweets(monkeypatch):
    captured = {}

    async def fake_run(query, limit):
        captured["query"] = query
        captured["limit"] = limit
        return [_tweet(1), _tweet(2)]

    monkeypatch.setattr(scraper_mod, "_run_search", fake_run)
    out = await scraper_mod.search("foo", limit=2)
    assert [t.id for t in out] == ["1", "2"]
    assert captured == {"query": "foo", "limit": 2}


@pytest.mark.asyncio
async def test_search_truncates_to_limit(monkeypatch):
    async def fake_run(query, limit):
        # X may return more than limit; orchestrator must truncate.
        return [_tweet(i) for i in range(5)]

    monkeypatch.setattr(scraper_mod, "_run_search", fake_run)
    out = await scraper_mod.search("foo", limit=3)
    assert [t.id for t in out] == ["0", "1", "2"]


@pytest.mark.asyncio
async def test_search_logs_start_and_done(monkeypatch, caplog):
    import logging

    async def fake_run(query, limit):
        return [_tweet(1)]

    monkeypatch.setattr(scraper_mod, "_run_search", fake_run)
    with caplog.at_level(logging.INFO, logger="xscraper.scraper"):
        await scraper_mod.search("foo", limit=5)
    msgs = [r.getMessage() for r in caplog.records if r.name == "xscraper.scraper"]
    assert any("search start" in m for m in msgs)
    assert any("search done" in m for m in msgs)
