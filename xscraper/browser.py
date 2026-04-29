"""Browser transport: drive a logged-in patchright Chromium and return the raw
SearchTimeline GraphQL response.

The browser handles all auth, headers, cookies, doc_id, features, and TLS
fingerprinting on its own. We attach a response listener BEFORE navigating so
we don't race the request, then return whatever JSON the browser fetched for
itself. Knows nothing about Tweet or any GraphQL shape.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

from patchright.async_api import async_playwright
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from xscraper.exceptions import XAuthError, XConfigError, XTimeoutError

log = logging.getLogger("xscraper.browser")

_SEARCH_URL_TEMPLATE = "https://x.com/search?q={q}&src=typed_query&f=live"
_RESPONSE_TIMEOUT_MS = 30_000
_LOGIN_URL_MARKERS = ("/login", "/i/flow/login")


@asynccontextmanager
async def fetch_search_timeline(
    query: str, *, state_path: Path, headed: bool = False
):
    """Navigate to Latest search and yield first SearchTimeline JSON.

    Browser stays open for the duration of the async with block, then closes.

    Raises:
        XConfigError: state_path doesn't exist
        XAuthError: Login wall hit or login timeout
        XTimeoutError: SearchTimeline response never fired
    """
    if not state_path.exists():
        raise XConfigError(
            f"{state_path} not found — run `python -m xscraper login` first"
        )

    url = _SEARCH_URL_TEMPLATE.format(q=quote(query, safe=""))
    log.info("launching chromium headed=%s", headed)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        try:
            ctx = await browser.new_context(storage_state=str(state_path))
            page = await ctx.new_page()

            async with page.expect_response(
                lambda r: "SearchTimeline" in r.url and r.status == 200,
                timeout=_RESPONSE_TIMEOUT_MS,
            ) as response_info:
                await page.goto(url, wait_until="domcontentloaded")
                try:
                    response = await response_info.value
                except PlaywrightTimeoutError as exc:
                    current = page.url
                    if any(m in current for m in _LOGIN_URL_MARKERS):
                        raise XAuthError(
                            "state.json rejected — re-run "
                            "`python -m xscraper login`"
                        ) from exc
                    raise XTimeoutError(
                        "SearchTimeline response never fired within 30s"
                    ) from exc

            yield await response.json()  # browser stays open until caller exits
        finally:
            await browser.close()