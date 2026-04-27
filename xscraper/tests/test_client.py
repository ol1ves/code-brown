"""XClient transport unit tests using httpx.MockTransport."""

from __future__ import annotations

import pytest
import httpx

from xscraper.client import XClient
from xscraper.config import Config
from xscraper.exceptions import XAuthError, XRateLimit


def _cfg() -> Config:
    return Config(
        auth_token="tok",
        ct0="csrf",
        bearer="bearer-x",
        user_agent="ua/1",
    )


def _transport(handler):
    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_get_graphql_returns_parsed_json():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, json={"data": {"ok": True}})

    async with XClient(_cfg(), transport=_transport(handler)) as client:
        out = await client.get_graphql("https://x.com/i/api/graphql/X/SearchTimeline", {"variables": "{}", "features": "{}"})

    assert out == {"data": {"ok": True}}
    req = captured["req"]
    assert req.headers["authorization"] == "Bearer bearer-x"
    assert req.headers["x-csrf-token"] == "csrf"
    assert "auth_token=tok" in req.headers["cookie"]
    assert "ct0=csrf" in req.headers["cookie"]
    assert req.headers["user-agent"] == "ua/1"


@pytest.mark.asyncio
async def test_get_graphql_401_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"errors": [{"code": 32}]})

    async with XClient(_cfg(), transport=_transport(handler)) as client:
        with pytest.raises(XAuthError, match="cookies rejected"):
            await client.get_graphql("https://x.com/i/api/graphql/X/SearchTimeline", {})


@pytest.mark.asyncio
async def test_get_graphql_403_raises_auth_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    async with XClient(_cfg(), transport=_transport(handler)) as client:
        with pytest.raises(XAuthError):
            await client.get_graphql("https://x.com/i/api/graphql/X/SearchTimeline", {})


@pytest.mark.asyncio
async def test_get_graphql_429_raises_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    async with XClient(_cfg(), transport=_transport(handler)) as client:
        with pytest.raises(XRateLimit, match="rate-limited"):
            await client.get_graphql("https://x.com/i/api/graphql/X/SearchTimeline", {})


@pytest.mark.asyncio
async def test_get_graphql_500_raises_httpx_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    async with XClient(_cfg(), transport=_transport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await client.get_graphql("https://x.com/i/api/graphql/X/SearchTimeline", {})


@pytest.mark.asyncio
async def test_get_graphql_passes_query_params():
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return httpx.Response(200, json={})

    async with XClient(_cfg(), transport=_transport(handler)) as client:
        await client.get_graphql(
            "https://x.com/i/api/graphql/X/SearchTimeline",
            {"variables": '{"a":1}', "features": "{}"},
        )

    url = str(captured["req"].url)
    assert "variables=" in url
    assert "features=" in url
