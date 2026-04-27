"""Static config + env loader for xscraper.

All required env vars are documented in xscraper/.env.example. Any value that
falls back to a default emits an INFO log line on load_config() — silent
defaults are forbidden so when something breaks we know which constants were
in play.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from xscraper.exceptions import XConfigError

_log = logging.getLogger("xscraper.config")

# Public web-app bearer. Hardcoded by the x.com web client; observed stable for
# years. Override via X_BEARER env if X ever rotates it.
DEFAULT_BEARER = (
    "AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# Pinned modern Chrome UA. Last verified 2026-04-27.
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

GRAPHQL_BASE = "https://x.com/i/api/graphql"


@dataclass(frozen=True)
class Config:
    auth_token: str
    ct0: str
    bearer: str
    user_agent: str


def _load_dotenv_from_xscraper() -> None:
    """Load xscraper/.env without polluting siblings. Idempotent — load_dotenv
    silently no-ops if the path does not exist."""
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path, override=False)


def load_config() -> Config:
    """Read xscraper/.env and process env. Logs each defaulted fallback."""
    _load_dotenv_from_xscraper()

    auth_token = os.environ.get("X_AUTH_TOKEN", "").strip()
    ct0 = os.environ.get("X_CT0", "").strip()
    if not auth_token:
        raise XConfigError(
            "X_AUTH_TOKEN must be set in xscraper/.env "
            "(export from a logged-in browser session)"
        )
    if not ct0:
        raise XConfigError(
            "X_CT0 must be set in xscraper/.env "
            "(export from a logged-in browser session)"
        )

    bearer = os.environ.get("X_BEARER", "").strip()
    if not bearer:
        _log.info(
            "X_BEARER not set in env, using default web-app constant "
            "(last verified 2026-04-27)"
        )
        bearer = DEFAULT_BEARER

    return Config(
        auth_token=auth_token,
        ct0=ct0,
        bearer=bearer,
        user_agent=DEFAULT_USER_AGENT,
    )


def build_request_headers(cfg: Config) -> dict[str, str]:
    """Headers required for every authenticated GraphQL call."""
    return {
        "authorization": f"Bearer {cfg.bearer}",
        "x-csrf-token": cfg.ct0,
        "cookie": f"auth_token={cfg.auth_token}; ct0={cfg.ct0}",
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "content-type": "application/json",
        "user-agent": cfg.user_agent,
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
    }
