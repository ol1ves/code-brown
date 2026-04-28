"""Browser transport: drive a logged-in patchright Chromium and return the raw
SearchTimeline GraphQL response.

The browser handles all auth, headers, cookies, doc_id, features, and TLS
fingerprinting on its own. We attach a response listener BEFORE navigating so
we don't race the request, then return whatever JSON the browser fetched for
itself. Knows nothing about Tweet or any GraphQL shape.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

from patchright.async_api import async_playwright
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from xscraper.exceptions import XAuthError, XConfigError, XTimeoutError

log = logging.getLogger("xscraper.browser")

_SEARCH_URL_TEMPLATE = "https://x.com/search?q={q}&src=typed_query&f=live"
_RESPONSE_TIMEOUT_MS = 30_000
_LOGIN_URL_MARKERS = ("/login", "/i/flow/login")


async def fetch_search_timeline(
    query: str, *, state_path: Path, headed: bool = False
) -> dict:
    """Navigate to Latest search and return first SearchTimeline JSON.
    
    Args:
        query: Search term
        state_path: Path to patchright storage_state.json
        headed: Show browser window (default headless)
    
    Returns:
        Raw JSON dict from SearchTimeline response
    
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
            
            # Attach listener BEFORE goto() to avoid race
            response_promise = page.wait_for_response(
                lambda r: "SearchTimeline" in r.url and r.status == 200,
                timeout=_RESPONSE_TIMEOUT_MS,
            )
            await page.goto(url, wait_until="domcontentloaded")
            
            try:
                response = await response_promise
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
            
            return await response.json()
        finally:
            await browser.close()