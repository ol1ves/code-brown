"""Exception hierarchy for xscraper.

Exit codes:
  1 — XAuthError (login wall hit or login timeout)
  3 — XSchemaError (response shape changed)
  4 — XConfigError (missing env/state.json)
  5 — XTimeoutError (SearchTimeline response timeout)
  6 — Generic/unhandled exceptions (re-raised)
"""

from __future__ import annotations


class XError(Exception):
    """Base exception for xscraper."""

    pass


class XConfigError(XError):
    """Missing or invalid configuration (e.g., state.json not found).

    Exit code: 4
    """

    pass


class XAuthError(XError):
    """Login wall hit or login timeout (session expired).

    Exit code: 1
    """

    pass


class XTimeoutError(XError):
    """SearchTimeline response timeout (response never fired within timeout).

    Exit code: 5
    """

    pass


class XSchemaError(XError):
    """Response shape changed (parser no longer recognizes SearchTimeline response).

    Exit code: 3
    """

    pass
