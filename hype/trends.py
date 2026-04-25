"""Google Trends fetcher for hype signal."""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from typing import Literal

import pandas as pd
from pytrends.exceptions import TooManyRequestsError
from pytrends.request import TrendReq

from shared.models import TrendPoint, TrendSeries

RANGE_TO_TIMEFRAME: dict[str, str] = {
    "7d": "now 7-d",
    "30d": "today 1-m",
    "90d": "today 3-m",
}

_MAX_429_RETRIES = 3
_429_BACKOFF_SECONDS = 1.5


def _build_client() -> TrendReq:
    # urllib3 >=2.0 broke pytrends' Retry construction (method_whitelist kwarg
    # was renamed); skip retries=/backoff_factor= and retry 429s manually below.
    kwargs: dict = {"hl": "en-US", "tz": 0}
    proxy = os.environ.get("TRENDS_PROXY", "").strip()
    if proxy:
        kwargs["proxies"] = [proxy]
    return TrendReq(**kwargs)


def _to_daily_points(frame: pd.DataFrame, term: str, range: str) -> list[TrendPoint]:
    """Convert a pytrends interest_over_time DataFrame to daily TrendPoints."""
    if frame.empty or term not in frame.columns:
        return []

    series = frame[term]

    if range == "7d":
        series = series.copy()
        series.index = pd.to_datetime(series.index, utc=True)
        daily = series.resample("1D").mean().dropna()
    else:
        daily = series.copy()
        daily.index = pd.to_datetime(daily.index, utc=True)

    points: list[TrendPoint] = []
    for ts, val in daily.items():
        if pd.isna(val):
            continue
        midnight = datetime(ts.year, ts.month, ts.day, tzinfo=UTC)
        points.append(
            TrendPoint(
                day_unix=int(midnight.timestamp()),
                intensity=int(round(float(val))),
            )
        )
    return points


def _try_fetch(term: str, range: Literal["7d", "30d", "90d"]) -> list[TrendPoint]:
    timeframe = RANGE_TO_TIMEFRAME[range]
    last_exc: Exception | None = None
    attempt = 0
    while attempt < _MAX_429_RETRIES:
        try:
            client = _build_client()
            client.build_payload([term], cat=0, timeframe=timeframe, geo="", gprop="")
            frame = client.interest_over_time()
            return _to_daily_points(frame, term=term, range=range)
        except TooManyRequestsError as exc:
            last_exc = exc
            time.sleep(_429_BACKOFF_SECONDS * (attempt + 1))
            attempt += 1
    if last_exc is not None:
        raise last_exc
    return []


def fetch(term: str, range: Literal["7d", "30d", "90d"]) -> TrendSeries:
    """Blocking fetch. Returns a TrendSeries with daily buckets, oldest -> newest.

    When the original term yields no points (common for long-tail queries
    Google Trends has no signal on), progressively drop trailing tokens
    until either we get data or we've exhausted broader prefixes.
    """
    tokens = term.split()
    points: list[TrendPoint] = []
    for cutoff in range_tokens(len(tokens)):
        broader = " ".join(tokens[:cutoff])
        if not broader:
            continue
        try:
            points = _try_fetch(broader, range)
        except Exception:
            points = []
        if points:
            break
    return TrendSeries(range=range, points=points)


def range_tokens(n: int) -> list[int]:
    """Order: full-length first, then progressively shorter prefixes down to 1."""
    return list(range(n, 0, -1))

