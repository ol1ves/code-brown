"""CLI for xscraper.

Usage:
    python -m xscraper.cli "<query>" [--limit N] [--json]

Exit codes (mirrors docs/superpowers/specs/2026-04-27-xscraper-design.md §7.4):
    0  success
    1  XAuthError       (cookies rejected)
    2  argparse error   (reserved by argparse default)
    3  XSchemaError     (parser failed; doc_id likely rotated)
    4  XConfigError     (missing required env var)
    5  XRateLimit       (429)
    6  uncaught httpx error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from datetime import UTC, datetime
import shutil
import textwrap

import httpx

from xscraper.exceptions import (
    XAuthError,
    XConfigError,
    XRateLimit,
    XSchemaError,
)
from xscraper.models import Tweet
from xscraper.scraper import search

_log = logging.getLogger("xscraper.cli")

LIMIT_MAX = 20


def _positive_int_max(max_value: int):
    def _parse(raw: str) -> int:
        try:
            n = int(raw)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid int: {raw!r}") from exc
        if n < 1 or n > max_value:
            raise argparse.ArgumentTypeError(
                f"must be between 1 and {max_value}, got {n}"
            )
        return n

    return _parse


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="xscraper",
        description="Search X Latest tab and print up to N tweets.",
    )
    p.add_argument("query", help="Search term (quote multi-word).")
    p.add_argument(
        "--limit",
        "-l",
        type=_positive_int_max(LIMIT_MAX),
        default=LIMIT_MAX,
        help=f"Number of tweets to return (1..{LIMIT_MAX}). Default {LIMIT_MAX}.",
    )
    p.add_argument(
        "--raw",
        action="store_true",
        help="Emit raw JSON array instead of pretty text (default: pretty).",
    )
    return p


def _compact(n: int) -> str:
    """1500 -> '1.5k', 15_000_000 -> '15M'."""
    if n < 1_000:
        return str(n)
    if n < 1_000_000:
        v = n / 1_000
        return f"{v:.1f}k" if v < 10 else f"{int(v)}k"
    v = n / 1_000_000
    return f"{v:.1f}M" if v < 10 else f"{int(v)}M"


def _human_relative(ts_seconds: int) -> str:
    now = datetime.now(tz=UTC)
    then = datetime.fromtimestamp(ts_seconds, tz=UTC)
    delta = now - then
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s"
    mins = secs // 60
    if mins < 60:
        return f"{mins}m"
    hrs = mins // 60
    if hrs < 24:
        return f"{hrs}h"
    days = hrs // 24
    if days < 7:
        return f"{days}d"
    return then.strftime("%Y-%m-%d")


def _render_plain(tweets: list[Tweet]) -> str:
    # Pretty terminal rendering: bold author, dim metadata, wrapped text.
    use_color = sys.stdout.isatty()

    def _bold(s: str) -> str:
        return f"\x1b[1m{s}\x1b[0m" if use_color else s

    def _dim(s: str) -> str:
        return f"\x1b[2m{s}\x1b[0m" if use_color else s

    width = shutil.get_terminal_size((80, 20)).columns
    wrap_width = max(20, width - 4)

    blocks: list[str] = []
    for t in tweets:
        rel = _human_relative(t.created_at)
        meta = (
            f"{_compact(t.like_count)}❤ { _compact(t.retweet_count)}🔁 "
            f"{_compact(t.reply_count)}💬 { _compact(t.quote_count)}❝"
        )
        header = f"{_bold('@' + t.handle)} {_dim('·')} {_dim(rel)} {_dim('·')} {_dim(t.lang)} {_dim('·')} {_dim(meta)}"

        text = " ".join(t.text.splitlines())
        wrapped = textwrap.fill(text, width=wrap_width)
        blocks.append(f"{header}\n{wrapped}")

    return "\n\n".join(blocks)


def _render_json(tweets: list[Tweet]) -> str:
    return json.dumps([asdict(t) for t in tweets], indent=2)


def _configure_logging() -> None:
    """Minimal stdlib logging setup for CLI runs.

    Default: INFO to stderr, plain key=value style. xscraper does not import
    backend.logging_setup — it intentionally keeps its own minimal formatter
    so the module stays self-contained.
    """
    if logging.getLogger().handlers:
        return  # already configured (e.g. by a test harness)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
    )
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # Suppress very verbose HTTP client logs by default; keep our own INFO.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def main(argv: list[str] | None = None) -> int:
    _configure_logging()
    args = _build_parser().parse_args(argv)

    try:
        tweets = asyncio.run(search(args.query, args.limit))
    except XAuthError as e:
        _log.error("XAuthError: %s", e)
        print(f"error: {e}", file=sys.stderr)
        return 1
    except XSchemaError as e:
        _log.error("XSchemaError: %s", e)
        print(f"error: {e}", file=sys.stderr)
        return 3
    except XConfigError as e:
        _log.error("XConfigError: %s", e)
        print(f"error: {e}", file=sys.stderr)
        return 4
    except XRateLimit as e:
        _log.error("XRateLimit: %s", e)
        print(f"error: {e}", file=sys.stderr)
        return 5
    except httpx.HTTPError as e:
        _log.error("httpx error: %s", e)
        print(f"network error: {e}", file=sys.stderr)
        return 6

    if args.raw:
        print(_render_json(tweets))
    else:
        print(_render_plain(tweets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
