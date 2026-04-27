"""Async HTTP client for xscraper. Wraps httpx.AsyncClient with the
auth/cookie/UA headers X requires. No retry layer — raises clearly on the
distinct failure modes that matter (auth, rate limit, schema)."""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from xscraper.config import Config, build_request_headers
from xscraper.exceptions import XAuthError, XRateLimit

REQUEST_TIMEOUT_SEC = 20.0


class XClient:
    """Single-session async client. Use as ``async with XClient(cfg) as c:``.

    ``transport`` is exposed for tests to inject ``httpx.MockTransport``.
    """

    def __init__(
        self,
        cfg: Config,
        *,
        timeout: float = REQUEST_TIMEOUT_SEC,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._cfg = cfg
        self._timeout = timeout
        self._transport = transport
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "XClient":
        self._client = httpx.AsyncClient(
            timeout=self._timeout,
            headers=build_request_headers(self._cfg),
            follow_redirects=False,
            transport=self._transport,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get_graphql(self, url: str, params: dict[str, str]) -> Any:
        """GET a GraphQL endpoint with query-param variables/features.

        Raises:
            XAuthError on 401/403.
            XRateLimit on 429.
            httpx.HTTPStatusError on other 4xx/5xx.
        """
        if self._client is None:
            raise RuntimeError("XClient not entered")
        response = await self._client.get(url, params=params)
        if response.status_code in (401, 403):
            raise XAuthError(
                f"cookies rejected ({response.status_code}) — "
                "refresh xscraper/.env from a logged-in browser session"
            )
        if response.status_code == 429:
            raise XRateLimit(
                "rate-limited by X — wait or use a fresh account"
            )
        response.raise_for_status()
        return response.json()
