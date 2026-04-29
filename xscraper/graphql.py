"""SearchTimeline response parser.

This is the most fragile file in xscraper alongside browser.py. X's GraphQL
response shape rotates periodically. When XSchemaError fires, capture a fresh
SearchTimeline response from DevTools and update both this parser and the
fixture in xscraper/tests/fixtures/search_latest.json.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from xscraper.exceptions import XSchemaError
from xscraper.models import Tweet

_X_TS_FORMAT = "%a %b %d %H:%M:%S %z %Y"

def parse_search_response(raw: dict[str, Any]) -> list[Tweet]:
    """Walk SearchTimeline response, return list[Tweet].
    
    Raises XSchemaError if:
    - Response path structure is wrong
    - No tweet entries found
    """
    # Navigate to instructions
    try:
        instructions = raw["data"]["search_by_raw_query"]["search_timeline"][
            "timeline"
        ]["instructions"]
    except (KeyError, TypeError) as exc:
        raise XSchemaError(
            "SearchTimeline response missing data.search_by_raw_query."
            "search_timeline.timeline.instructions — response shape changed; "
            "refresh xscraper/graphql.py parser"
        ) from exc
    
    if not isinstance(instructions, list):
        raise XSchemaError("instructions is not a list")
    
    tweets: list[Tweet] = []
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        entries = instruction.get("entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            tweet = _entry_to_tweet(entry)
            if tweet is not None:
                tweets.append(tweet)
    
    if not tweets:
        raise XSchemaError(
            "SearchTimeline response had instructions but no parseable tweet "
            "entries — response shape changed; refresh xscraper/graphql.py parser"
        )
    return tweets

def _entry_to_tweet(entry: Any) -> Tweet | None:
    """Convert entry to Tweet, or None to skip it."""
    if not isinstance(entry, dict):
        return None
    entry_id = entry.get("entryId", "")
    if not entry_id.startswith("tweet-"):
        return None  # skip cursors and other entries
    
    try:
        result = entry["content"]["itemContent"]["tweet_results"]["result"]
        legacy = result["legacy"]
        user_core = result["core"]["user_results"]["result"]["core"]
        print(user_core, "\n") 
        return Tweet(
            id=str(result["rest_id"]),
            text=legacy["full_text"],
            created_at=int(
                datetime.strptime(
                    legacy["created_at"], _X_TS_FORMAT
                ).timestamp()
            ),
            handle=user_core["screen_name"],
            lang=legacy.get("lang", "") or "",
            like_count=int(legacy["favorite_count"]),
            retweet_count=int(legacy["retweet_count"]),
            reply_count=int(legacy["reply_count"]),
            quote_count=int(legacy["quote_count"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise XSchemaError(
            f"failed to parse tweet entry {entry_id!r}: {exc}"
        ) from exc