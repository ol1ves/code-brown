"""argparse entry for `python -m xscraper`.

Subcommands:
  search (default — bare positional query also routes here)
  login

Exit codes:
  0  success
  1  XAuthError
  2  argparse error (reserved by argparse)
  3  XSchemaError
  4  XConfigError
  5  XTimeoutError
  6  uncaught browser/transport error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from xscraper.config import load_config, setup_logging
from xscraper.exceptions import (
    XAuthError,
    XConfigError,
    XSchemaError,
    XTimeoutError,
)
from xscraper.login import run_login
from xscraper.models import Tweet
from xscraper.scraper import search

log = logging.getLogger("xscraper.cli")

_LIMIT_MIN = 1
_LIMIT_MAX = 20


def _limit_type(raw: str) -> int:
    """Validate limit argument is in range [1..20]."""
    n = int(raw)
    if not (_LIMIT_MIN <= n <= _LIMIT_MAX):
        raise argparse.ArgumentTypeError(
            f"limit must be between {_LIMIT_MIN} and {_LIMIT_MAX}"
        )
    return n


def _build_search_parser() -> argparse.ArgumentParser:
    """Build parser for search subcommand."""
    parser = argparse.ArgumentParser(
        description="Search X Latest tab",
        prog="python -m xscraper search",
        add_help=False,  # Avoid conflicts with main parser
    )
    parser.add_argument("query", help="search term (quote multi-word)")
    parser.add_argument(
        "-l",
        "--limit",
        type=_limit_type,
        default=_LIMIT_MAX,
        help=f"max tweets (1-{_LIMIT_MAX}, default {_LIMIT_MAX})",
    )
    parser.add_argument("--json", action="store_true", help="render as JSON")
    parser.add_argument("--headed", action="store_true", help="show browser window")
    return parser


def _build_login_parser() -> argparse.ArgumentParser:
    """Build parser for login subcommand."""
    parser = argparse.ArgumentParser(
        description="One-time login",
        prog="python -m xscraper login",
        add_help=False,
    )
    parser.add_argument("--headed", action="store_true", help="show browser (default)")
    return parser


def _compact(n: int) -> str:
    """Format count as compact string: 1500 -> 1.5k, 1000000 -> 1M."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".rstrip("0").rstrip(".")
    elif n >= 1_000:
        return f"{n / 1_000:.1f}k".rstrip("0").rstrip(".")
    return str(n)


def _render_plain(tweets: list[Tweet]) -> str:
    """Render tweets as plain text with compact counts."""
    blocks = []
    for t in tweets:
        created_iso = datetime.fromtimestamp(
            t.created_at, tz=timezone.utc
        ).isoformat()
        header = (
            f"@{t.handle} · {_compact(t.like_count)}❤ "
            f"{_compact(t.retweet_count)}🔁 {_compact(t.reply_count)}💬 "
            f"{_compact(t.quote_count)}❝ · {created_iso}"
        )
        blocks.append(f"{header}\n{t.text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _render_json(tweets: list[Tweet]) -> str:
    """Render tweets as JSON."""
    return json.dumps([asdict(t) for t in tweets], indent=2)


async def _run_search(args: argparse.Namespace) -> int:
    """Execute search and render output."""
    tweets = await search(args.query, args.limit, headed=args.headed)
    if args.json:
        print(_render_json(tweets))
    else:
        print(_render_plain(tweets), end="")
    return 0


async def _run_login(args: argparse.Namespace) -> int:
    """Execute login."""
    await run_login()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Main entry point for CLI.
    
    Routes to search or login based on first argument.
    """
    try:
        # Set up logging first
        cfg = load_config()
        setup_logging(cfg.log_format)
    except Exception:
        # If config fails, continue anyway (will fail later if needed)
        pass

    if argv is None:
        argv = sys.argv[1:]

    # Route based on first argument
    if not argv:
        # No args at all
        try:
            parser = _build_search_parser()
            parser.parse_args([])  # Will error: missing query
        except SystemExit:
            return 2  # argparse error
        return 2

    if argv[0] == "login":
        # Login subcommand
        try:
            parser = _build_login_parser()
            args = parser.parse_args(argv[1:])
            return asyncio.run(_run_login(args))
        except SystemExit as e:
            return e.code if isinstance(e.code, int) else 2
        except XAuthError as e:
            log.error("XAuthError: %s", e)
            return 1
        except XSchemaError as e:
            log.error("XSchemaError: %s", e)
            return 3
        except XConfigError as e:
            log.error("XConfigError: %s", e)
            return 4
        except XTimeoutError as e:
            log.error("XTimeoutError: %s", e)
            return 5
        except Exception as e:
            log.error("Unexpected error: %s", e, exc_info=True)
            return 6

    # Default to search (either explicit "search" or bare query)
    if argv[0] == "search":
        args_to_parse = argv[1:]
    else:
        args_to_parse = argv

    try:
        parser = _build_search_parser()
        args = parser.parse_args(args_to_parse)
        return asyncio.run(_run_search(args))
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    except XAuthError as e:
        log.error("XAuthError: %s", e)
        return 1
    except XSchemaError as e:
        log.error("XSchemaError: %s", e)
        return 3
    except XConfigError as e:
        log.error("XConfigError: %s", e)
        return 4
    except XTimeoutError as e:
        log.error("XTimeoutError: %s", e)
        return 5
    except Exception as e:
        log.error("Unexpected error: %s", e, exc_info=True)
        return 6


if __name__ == "__main__":
    sys.exit(main())