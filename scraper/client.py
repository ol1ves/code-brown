"""Async Grailed HTTP client with retry and rate-limit handling."""

from __future__ import annotations

import asyncio
import random
from types import TracebackType
from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from scraper.config import (
    BROWSER_HEADERS_HTML,
    BROWSER_HEADERS_JSON,
    DEFAULT_HEADERS,
    GRAILED_BASE_URL,
    MAX_CONCURRENCY,
    REQUEST_DELAY_RANGE,
    REQUEST_TIMEOUT_SEC,
    USER_AGENTS,
)
from scraper.exceptions import GrailedRateLimitExceeded

class _RateLimited(Exception):
    """Internal marker exception for HTTP 429."""


class _ServerError(Exception):
    """Internal marker exception for HTTP 5xx."""


class GrailedClient:
    """Async HTTP client with throttle, UA rotation, and retry semantics."""

    def __init__(
        self,
        *,
        delay_range: tuple[float, float] = REQUEST_DELAY_RANGE,
        max_concurrency: int = MAX_CONCURRENCY,
        timeout: float = REQUEST_TIMEOUT_SEC,
        retry_wait_initial: float = 30.0,
        max_429_attempts: int = 3,
        max_5xx_attempts: int = 3,
    ) -> None:
        self._delay_range = delay_range
        self._sem = asyncio.Semaphore(max_concurrency)
        self._timeout = timeout
        self._retry_wait_initial = retry_wait_initial
        self._max_429_attempts = max_429_attempts
        self._max_5xx_attempts = max_5xx_attempts
        self._client: httpx.AsyncClient | None = None
        self._user_agent: str = random.choice(USER_AGENTS)
        self._warmed_up: bool = False
        self._warmup_lock: asyncio.Lock = asyncio.Lock()

    async def __aenter__(self) -> "GrailedClient":
        self._client = httpx.AsyncClient(
            http2=True,
            timeout=self._timeout,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
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

    async def get_json(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        *,
        throttle: bool = True,
    ) -> Any:
        """GET the URL and return decoded JSON with retry semantics.

        ``throttle=False`` skips the inter-request jitter delay (use for trusted
        APIs like Algolia that don't need anti-bot pacing).
        """
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((_RateLimited, _ServerError)),
                wait=wait_exponential(multiplier=self._retry_wait_initial, max=120),
                stop=stop_after_attempt(
                    max(self._max_429_attempts, self._max_5xx_attempts)
                ),
                reraise=True,
            ):
                with attempt:
                    return await self._do_get(url, params, headers, throttle=throttle)
        except RetryError as exc:
            raise GrailedRateLimitExceeded(str(exc)) from exc
        except _RateLimited as exc:
            raise GrailedRateLimitExceeded(str(exc)) from exc

    async def get_listing_detail(self, listing_id: str) -> Any:
        """Fetch full listing detail JSON (includes description) from Grailed.

        Performs a one-shot warm-up against the public site to seed Cloudflare
        cookies; subsequent calls reuse the cookie jar.
        """
        await self._ensure_warmed_up()
        url = f"https://www.grailed.com/api/listings/{listing_id}"
        return await self.get_json(url, headers=BROWSER_HEADERS_JSON)

    async def _ensure_warmed_up(self) -> None:
        if self._warmed_up:
            return
        async with self._warmup_lock:
            if self._warmed_up:
                return
            if self._client is None:
                raise RuntimeError("GrailedClient not entered")
            headers = {"User-Agent": self._user_agent, **BROWSER_HEADERS_HTML}
            try:
                await self._client.get(GRAILED_BASE_URL, headers=headers)
            except httpx.HTTPError:
                pass
            self._warmed_up = True

    async def post_json(
        self,
        url: str,
        json_payload: Any,
        headers: dict[str, str] | None = None,
        *,
        throttle: bool = True,
    ) -> Any:
        """POST JSON to the URL and return decoded JSON with retry semantics.

        ``throttle=False`` skips the inter-request jitter delay (use for trusted
        APIs like Algolia that don't need anti-bot pacing).
        """
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type((_RateLimited, _ServerError)),
                wait=wait_exponential(multiplier=self._retry_wait_initial, max=120),
                stop=stop_after_attempt(
                    max(self._max_429_attempts, self._max_5xx_attempts)
                ),
                reraise=True,
            ):
                with attempt:
                    return await self._do_post(url, json_payload, headers, throttle=throttle)
        except RetryError as exc:
            raise GrailedRateLimitExceeded(str(exc)) from exc
        except _RateLimited as exc:
            raise GrailedRateLimitExceeded(str(exc)) from exc

    async def _do_get(
        self,
        url: str,
        params: dict[str, Any] | None,
        extra_headers: dict[str, str] | None,
        *,
        throttle: bool = True,
    ) -> Any:
        if self._client is None:
            raise RuntimeError("GrailedClient not entered")

        headers = {"User-Agent": self._user_agent}
        if extra_headers is not None:
            headers.update(extra_headers)

        async with self._sem:
            response = await self._client.get(url, params=params, headers=headers)
            if throttle:
                await asyncio.sleep(random.uniform(*self._delay_range))

        if response.status_code == 429:
            raise _RateLimited(f"429 response from {url}")
        if 500 <= response.status_code < 600:
            raise _ServerError(f"{response.status_code} response from {url}")

        response.raise_for_status()
        return response.json()

    async def _do_post(
        self,
        url: str,
        json_payload: Any,
        extra_headers: dict[str, str] | None,
        *,
        throttle: bool = True,
    ) -> Any:
        if self._client is None:
            raise RuntimeError("GrailedClient not entered")

        headers = {"User-Agent": self._user_agent}
        if extra_headers is not None:
            headers.update(extra_headers)

        async with self._sem:
            response = await self._client.post(url, json=json_payload, headers=headers)
            if throttle:
                await asyncio.sleep(random.uniform(*self._delay_range))

        if response.status_code == 429:
            raise _RateLimited(f"429 response from {url}")
        if 500 <= response.status_code < 600:
            raise _ServerError(f"{response.status_code} response from {url}")

        response.raise_for_status()
        return response.json()
