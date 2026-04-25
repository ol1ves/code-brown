"""CLI test harness for the backend orchestrator.

  python -m backend.cli search        # interactive SearchParams prompt
  python -m backend.cli hype <term>   # one-shot hype lookup

This file contains zero business logic. It exists to drive
``backend.orchestrator`` from a terminal so we can verify wiring before
any HTTP handlers are written.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from backend import orchestrator
from ev.ev import set_store as set_ev_store
from hype.cli import _print_summary as _print_hype_summary
from scraper.cli import _prompt_params
from scraper.scraper import set_store as set_scraper_store
from shared.models import Recommendation, SearchResponse
from shared.store import ListingStore, set_recommendations_store


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="CLI harness for backend orchestrator.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    search_parser = subparsers.add_parser("search", help="Run search flow")
    search_parser.add_argument("--json", action="store_true", help="Print raw JSON response")
    search_parser.add_argument(
        "--no-persist",
        action="store_true",
        help="Skip writing sold comparables to the ListingStore (persist is on by default)",
    )

    hype_parser = subparsers.add_parser("hype", help="Run hype flow")
    hype_parser.add_argument("term", help="Term to evaluate")
    hype_parser.add_argument("--json", action="store_true", help="Print raw JSON response")

    return parser


def _fmt_money(value: float | int) -> str:
    return f"${float(value):.2f}"


def _print_ranked_line(item: Recommendation, idx: int, total: int) -> None:
    live = item.live_listing
    val = item.valuation
    dist = val["dist"]
    metrics = val["metrics"]
    sp = item.sell_probability

    print(f"[{idx}/{total}] {live.designer} {live.name}  (id={live.id})  url={live.url}")
    print(
        " ".join(
            [
                f"cost={_fmt_money(item.cost)}",
                f"q10={_fmt_money(dist['q10'])}",
                f"q50={_fmt_money(item.q50)}",
                f"q90={_fmt_money(dist['q90'])}",
                f"edge={_fmt_money(item.edge_usd)} ({metrics['percent_under']:.2f}%)",
                f"confidence={item.confidence}",
                f"effective_n={metrics['effective_n']}",
            ]
        )
    )
    q50_comp = sp.get("q50_comp_price")
    print(
        " ".join(
            [
                f"p_sell={item.p_sell:.4f}",
                f"median_days={sp['median_days_to_sell']:.2f}",
                f"adjusted_days={sp['adjusted_days_to_sell']:.2f}",
                f"pricing_ratio={sp['pricing_ratio']:.4f}",
                f"q50_comp={_fmt_money(q50_comp) if q50_comp is not None else '—'}",
                f"comps={sp['num_valid_time_comps']}/{sp['num_sold_comps']}",
            ]
        )
    )


def _print_search_response(response: SearchResponse) -> None:
    print("metadata")
    print(json.dumps(response.metadata.model_dump(mode="json"), indent=2))
    print()

    if not response.items:
        print("no rankable listings (all comp searches returned no_data)")
        return

    total = len(response.items)
    for idx, item in enumerate(response.items, start=1):
        _print_ranked_line(item, idx, total)
        if idx < total:
            print()


def _run_search(as_json: bool, persist: bool) -> int:
    try:
        params = _prompt_params()
    except (EOFError, KeyboardInterrupt):
        print("\naborted", file=sys.stderr)
        return 130

    response = asyncio.run(orchestrator.run_search(params, persist=persist))
    if as_json:
        print(response.model_dump_json(indent=2))
    else:
        _print_search_response(response)
    return 0


def _run_hype(term: str, as_json: bool) -> int:
    result = asyncio.run(orchestrator.run_hype(term))
    if as_json:
        print(result.model_dump_json(indent=2))
    else:
        _print_hype_summary(result)
    return 0


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
        if args.command == "search":
            persist = not args.no_persist
            if persist:
                _wire_stores()
            return _run_search(as_json=args.json, persist=persist)
        if args.command == "hype":
            return _run_hype(term=args.term, as_json=args.json)
        parser.print_help()
        return 1
    except Exception as exc:  # pragma: no cover
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())