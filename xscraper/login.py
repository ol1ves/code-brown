"""One-time login helper. Writes patchright storage_state to disk so subsequent
`python -m xscraper search` runs can reuse the session.

Always headed — login is inherently human-shaped (captcha, 2FA, "is this you?"
challenges). When X_USERNAME and X_PASSWORD are present, autofills the form;
otherwise the user types creds in the open window. Either way, the success
signal is the same: page lands on https://x.com/home within 5 minutes.
"""

from __future__ import annotations

import logging

from patchright.async_api import async_playwright
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from xscraper.config import load_config
from xscraper.exceptions import XAuthError

log = logging.getLogger("xscraper.login")

_LOGIN_URL = "https://x.com/login"
_HOME_URL = "https://x.com/home"
_LANDING_TIMEOUT_MS = 5 * 60_000  # 5 minutes
_CHALLENGE_FIELD_TIMEOUT_MS = 3_000


async def run_login() -> None:
    """Launch headed Chromium, autofill if envs set, wait for /home, save state."""
    cfg = load_config()
    autofill = bool(cfg.x_username and cfg.x_password)
    log.info("login start autofill=%s", autofill)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(_LOGIN_URL)

            if autofill:
                await _autofill(page, cfg.x_username, cfg.x_password)
            else:
                log.info(
                    "no credentials in env — log in manually in the browser window"
                )

            try:
                await page.wait_for_url(_HOME_URL, timeout=_LANDING_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                raise XAuthError(
                    "login did not complete within 5 minutes"
                ) from exc

            cfg.state_path.parent.mkdir(parents=True, exist_ok=True)
            await ctx.storage_state(path=str(cfg.state_path))
            log.info("state saved to %s", cfg.state_path)
        finally:
            await browser.close()


async def _autofill(page, username: str, password: str) -> None:
    """Best-effort autofill. If a selector misses, the user can still type
    manually in the open window — we never raise here."""
    try:
        await page.fill('input[autocomplete="username"]', username)
        await page.click('button:has-text("Next")')
    except PlaywrightTimeoutError:
        log.warning("username/Next selector missed — fill manually")
        return

    # X sometimes asks for username again on suspicious-login challenge.
    try:
        await page.wait_for_selector(
            'input[data-testid="ocfEnterTextTextInput"]',
            timeout=_CHALLENGE_FIELD_TIMEOUT_MS,
        )
        await page.fill(
            'input[data-testid="ocfEnterTextTextInput"]', username
        )
        await page.click('button:has-text("Next")')
    except PlaywrightTimeoutError:
        pass

    try:
        await page.fill('input[name="password"]', password)
        await page.click('button[data-testid="LoginForm_Login_Button"]')
    except PlaywrightTimeoutError:
        log.warning("password selector missed — fill manually")
