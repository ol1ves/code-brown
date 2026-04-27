"""X SearchTimeline GraphQL: doc_id, features dict, request builder, response
parser. This is the most fragile file in xscraper — DOC_ID and FEATURES rotate
every 2-4 weeks. When XSchemaError fires from the parser, refresh both from
DevTools → Network → SearchTimeline request.
"""

from __future__ import annotations

import json
from typing import Any

from xscraper.config import GRAPHQL_BASE

# Last verified 2026-04-27. Refresh from x.com web client when parser breaks.
DOC_ID = "nK1dw4oV3k4w5TdfMikt2w"
SEARCH_TIMELINE_OP = "SearchTimeline"

# Feature flags X requires on the SearchTimeline endpoint. Rotates with the
# web client. Last verified 2026-04-27. Copy from a fresh DevTools capture if
# the parser starts returning empty results or 4xx.
FEATURES: dict[str, bool] = {
    "rweb_video_screen_enabled": False,
    "profile_label_improvements_pcf_label_in_post_enabled": True,
    "rweb_tipjar_consumption_enabled": True,
    "responsive_web_graphql_exclude_directive_enabled": True,
    "verified_phone_label_enabled": False,
    "creator_subscriptions_tweet_preview_api_enabled": True,
    "responsive_web_graphql_timeline_navigation_enabled": True,
    "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
    "premium_content_api_read_enabled": False,
    "communities_web_enable_tweet_community_results_fetch": True,
    "c9s_tweet_anatomy_moderator_badge_enabled": True,
    "responsive_web_grok_analyze_button_fetch_trends_enabled": False,
    "responsive_web_grok_analyze_post_followups_enabled": True,
    "responsive_web_jetfuel_frame": False,
    "responsive_web_grok_share_attachment_enabled": True,
    "articles_preview_enabled": True,
    "responsive_web_edit_tweet_api_enabled": True,
    "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
    "view_counts_everywhere_api_enabled": True,
    "longform_notetweets_consumption_enabled": True,
    "responsive_web_twitter_article_tweet_consumption_enabled": True,
    "tweet_awards_web_tipping_enabled": False,
    "creator_subscriptions_quote_tweet_preview_enabled": False,
    "freedom_of_speech_not_reach_fetch_enabled": True,
    "standardized_nudges_misinfo": True,
    "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
    "rweb_video_timestamps_enabled": True,
    "longform_notetweets_rich_text_read_enabled": True,
    "longform_notetweets_inline_media_enabled": True,
    "responsive_web_grok_image_annotation_enabled": True,
    "responsive_web_enhance_cards_enabled": False,
}


def build_search_request(query: str, limit: int) -> tuple[str, dict[str, str]]:
    """Build the URL and query params for a SearchTimeline request.

    Returns ``(url, params)`` where ``params`` is the dict to pass to
    ``httpx.AsyncClient.get(..., params=params)``. httpx URL-encodes both
    ``variables`` and ``features`` automatically.
    """
    url = f"{GRAPHQL_BASE}/{DOC_ID}/{SEARCH_TIMELINE_OP}"
    variables: dict[str, Any] = {
        "rawQuery": query,
        "count": limit,
        "querySource": "typed_query",
        "product": "Latest",
    }
    params = {
        "variables": json.dumps(variables, separators=(",", ":")),
        "features": json.dumps(FEATURES, separators=(",", ":")),
    }
    return url, params


from datetime import datetime

from xscraper.exceptions import XSchemaError
from xscraper.models import Tweet

# X's created_at format: "Wed Apr 23 14:32:11 +0000 2026" — non-RFC, day-of-week
# first, year last. ``email.utils.parsedate_to_datetime`` does not handle this
# reliably; strptime does.
_X_TS_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def parse_search_response(raw: dict[str, Any]) -> list[Tweet]:
    """Walk the SearchTimeline response → list[Tweet].

    Raises XSchemaError if the shape is unrecognized OR if no tweet entries
    are found (empty success would be indistinguishable from a broken parser).
    """
    try:
        instructions = (
            raw["data"]["search_by_raw_query"]["search_timeline"]["timeline"][
                "instructions"
            ]
        )
    except (KeyError, TypeError) as exc:
        raise XSchemaError(
            "SearchTimeline response missing data.search_by_raw_query."
            "search_timeline.timeline.instructions — DOC_ID/features likely "
            "rotated; refresh xscraper/graphql.py from DevTools"
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
            if not isinstance(entry, dict):
                continue
            entry_id = entry.get("entryId", "")
            if not isinstance(entry_id, str) or not entry_id.startswith("tweet-"):
                continue
            tweet = _entry_to_tweet(entry)
            if tweet is not None:
                tweets.append(tweet)

    if not tweets:
        raise XSchemaError(
            "SearchTimeline response had instructions but no tweet entries — "
            "DOC_ID/features may have rotated, or the query genuinely returned "
            "nothing. Verify in a browser before treating this as success."
        )
    return tweets


def _entry_to_tweet(entry: dict[str, Any]) -> Tweet | None:
    """Pull a Tweet from a single ``tweet-*`` entry. Returns None if the
    nested shape is missing fields (a single bad entry should not abort the
    whole response — only a fully-empty result raises)."""
    try:
        result = entry["content"]["itemContent"]["tweet_results"]["result"]
        legacy = result["legacy"]
        user_legacy = result["core"]["user_results"]["result"]["legacy"]
    except (KeyError, TypeError):
        return None

    rest_id = result.get("rest_id")
    full_text = legacy.get("full_text")
    created_at_raw = legacy.get("created_at")
    handle = user_legacy.get("screen_name")
    if not isinstance(rest_id, str) or not isinstance(full_text, str):
        return None
    if not isinstance(created_at_raw, str) or not isinstance(handle, str):
        return None

    try:
        created_at = int(datetime.strptime(created_at_raw, _X_TS_FORMAT).timestamp())
    except (TypeError, ValueError):
        return None

    return Tweet(
        id=rest_id,
        text=full_text,
        created_at=created_at,
        handle=handle,
        lang=str(legacy.get("lang", "")),
        like_count=int(legacy.get("favorite_count", 0)),
        retweet_count=int(legacy.get("retweet_count", 0)),
        reply_count=int(legacy.get("reply_count", 0)),
        quote_count=int(legacy.get("quote_count", 0)),
    )
