"""CLI unit tests w/ monkeypatched search."""

from __future__ import annotations

import json

import pytest

from xscraper import cli as cli_mod
from xscraper.exceptions import (
    XAuthError,
    XConfigError,
    XRateLimit,
    XSchemaError,
)
from xscraper.models import Tweet


def _tweet(idx: int) -> Tweet:
    return Tweet(
        id=str(idx),
        text=f"tweet {idx}",
        created_at=1776594731 + idx,
        handle=f"u{idx}",
        lang="en",
        like_count=1500 * idx,
        retweet_count=200 * idx,
        reply_count=10 * idx,
        quote_count=3 * idx,
    )


def _patch_search(monkeypatch, fake):
    async def aw(query, limit):
        return fake(query, limit)

    monkeypatch.setattr(cli_mod, "search", aw)


def test_plain_output_contains_handles_and_text(monkeypatch, capsys):
    _patch_search(monkeypatch, lambda q, n: [_tweet(1), _tweet(2)])
    rc = cli_mod.main(["foo", "--limit", "2"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "@u1" in out
    assert "@u2" in out
    assert "tweet 1" in out
    assert "tweet 2" in out


def test_plain_output_compact_counts(monkeypatch, capsys):
    _patch_search(monkeypatch, lambda q, n: [_tweet(1)])
    cli_mod.main(["foo"])
    out = capsys.readouterr().out
    # 1500 likes -> 1.5k
    assert "1.5k" in out


def test_json_output_is_valid_array(monkeypatch, capsys):
    _patch_search(monkeypatch, lambda q, n: [_tweet(1), _tweet(2)])
    rc = cli_mod.main(["foo", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 2
    assert payload[0]["id"] == "1"
    assert payload[0]["like_count"] == 1500


def test_limit_too_high_rejected(monkeypatch, capsys):
    _patch_search(monkeypatch, lambda q, n: [])
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main(["foo", "--limit", "21"])
    assert exc_info.value.code == 2  # argparse default


def test_limit_zero_rejected(monkeypatch):
    _patch_search(monkeypatch, lambda q, n: [])
    with pytest.raises(SystemExit) as exc_info:
        cli_mod.main(["foo", "--limit", "0"])
    assert exc_info.value.code == 2


def test_default_limit_is_20(monkeypatch):
    captured = {}

    def fake(query, limit):
        captured["limit"] = limit
        return []

    async def aw(query, limit):
        return fake(query, limit)

    monkeypatch.setattr(cli_mod, "search", aw)
    # Should still exit non-zero because empty result + json renders []
    cli_mod.main(["foo", "--json"])
    assert captured["limit"] == 20


@pytest.mark.parametrize(
    "exc, code",
    [
        (XAuthError("x"), 1),
        (XSchemaError("x"), 3),
        (XConfigError("x"), 4),
        (XRateLimit("x"), 5),
    ],
)
def test_exit_codes_for_known_errors(monkeypatch, exc, code):
    async def aw(query, limit):
        raise exc

    monkeypatch.setattr(cli_mod, "search", aw)
    rc = cli_mod.main(["foo"])
    assert rc == code


def test_exit_code_for_httpx_error(monkeypatch):
    import httpx

    async def aw(query, limit):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(cli_mod, "search", aw)
    rc = cli_mod.main(["foo"])
    assert rc == 6
