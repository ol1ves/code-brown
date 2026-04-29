"""scraper.search orchestrator tests (browser monkeypatched)."""

from __future__ import annotations

import pytest

from xscraper import scraper
from xscraper.exceptions import XConfigError


@pytest.mark.asyncio
async def test_search_returns_parsed_tweets(monkeypatch, load_fixture, tmp_path):
    # Pretend state.json exists.
    state = tmp_path / "state.json"
    state.write_text("{}")
    monkeypatch.setenv("STATE_PATH", str(state))

    raw = load_fixture("search_latest.json")

    async def fake_fetch(query, *, state_path, headed):
        assert query == "macbook"
        assert state_path == state
        assert headed is False
        return raw

    monkeypatch.setattr(scraper, "fetch_search_timeline", fake_fetch)

    tweets = await scraper.search("macbook", 20, headed=False)
    assert len(tweets) == 1
    assert tweets[0].handle == "testuser"


@pytest.mark.asyncio
async def test_search_slices_to_limit(monkeypatch, load_fixture, tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{}")
    monkeypatch.setenv("STATE_PATH", str(state))

    raw = load_fixture("search_latest.json")

    async def fake_fetch(query, *, state_path, headed):
        return raw

    monkeypatch.setattr(scraper, "fetch_search_timeline", fake_fetch)
    tweets = await scraper.search("macbook", 0, headed=False)
    assert tweets == []


@pytest.mark.asyncio
async def test_search_raises_when_state_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "nope.json"))

    # browser.fetch_search_timeline will raise XConfigError on missing state
    async def fake_fetch(query, *, state_path, headed):
        from xscraper.exceptions import XConfigError
        raise XConfigError(f"{state_path} not found")

    monkeypatch.setattr(scraper, "fetch_search_timeline", fake_fetch)

    with pytest.raises(XConfigError):
        await scraper.search("macbook", 20, headed=False)
