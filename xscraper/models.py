"""xscraper data models. Frozen for immutable result values."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tweet:
    """A single tweet returned by SearchTimeline.

    ``id`` is a string because X tweet IDs exceed int64 in some langs and we
    never do arithmetic on them. ``created_at`` is unix seconds (parsed from
    X's "Wed Apr 23 14:32:11 +0000 2026" format).
    """

    id: str
    text: str
    created_at: int
    handle: str
    lang: str
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
