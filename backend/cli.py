"""Backend CLI.

Usage:
  python -m backend.cli search "<query>" <live_limit> <sold_limit> [--no-persist] [--json] [--no-color]
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from backend.logging_setup import configure_logging
from backend.pipeline.context import RunContext
from backend.pipeline.search import run_search
from backend.presenter import render_search_result
from ev.ev import set_store as set_ev_store
from scraper.scraper import set_store as set_scraper_store
from shared.models import SearchParams
from shared.store import ListingStore, set_recommendations_store


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI for backend search pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Run search flow")
    search_parser.add_argument("query", type=str)
    search_parser.add_argument("live_limit", type=int)
    search_parser.add_argument("sold_limit", type=int)
    search_parser.add_argument("--json", action="store_true", help="Print raw JSON response")
    search_parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip writing recommendations to Supabase",
    )
    search_parser.add_argument("--no-color", action="store_true", help="Disable ANSI colors in presenter output")

    return parser


def _wire_stores() -> None:
    """Wire the ListingStore for scraper + EV. Mirrors ``backend.main`` lifespan
    so the CLI test harness can persist sold comparables to Supabase."""
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env "
            "(pass --no-persist to skip)"
        )
    from supabase import create_client

    store = ListingStore(create_client(url, key))
    set_scraper_store(store)
    set_ev_store(store)
    set_recommendations_store(store)


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
        if args.command == "search":
            persist = not args.no_persist
            if persist:
                _wire_stores()
            params = SearchParams(
                query=args.query,
                live_limit=args.live_limit,
                sold_limit=args.sold_limit,
            )
            ctx = RunContext()
            response = asyncio.run(run_search(params, ctx, persist=persist))
            if args.json:
                print(response.model_dump_json(indent=2))
            else:
                print(render_search_result(response, ctx, use_color=not args.no_color))
            return 0
        parser.print_help()
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())