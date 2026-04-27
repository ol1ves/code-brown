"""xscraper-specific exceptions.

Each maps to a distinct CLI exit code in xscraper/cli.py:
  XAuthError    -> 1
  XSchemaError  -> 3
  XConfigError  -> 4
  XRateLimit    -> 5
"""

from __future__ import annotations


class XError(Exception):
    """Base for all xscraper errors."""


class XConfigError(XError):
    """Required env var missing or malformed."""


class XAuthError(XError):
    """X rejected our cookies (HTTP 401/403)."""


class XRateLimit(XError):
    """X rate-limited the request (HTTP 429)."""


class XSchemaError(XError):
    """Response shape unrecognized; DOC_ID/features likely rotated."""
