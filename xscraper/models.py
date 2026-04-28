"""Data models for xscraper."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tweet:
    """Immutable representation of a tweet."""

    id: str
    text: str
    created_at: int  # unix seconds
    handle: str
    lang: str
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
