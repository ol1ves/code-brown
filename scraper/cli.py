"""Interactive CLI for testing the scraper. Prompts each SearchParams field
and prints structured results to stdout. ``--persist`` wires a Supabase-backed
ListingStore so cache reads + write-through happen during the run."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from dotenv import load_dotenv

load_dotenv()

from scraper.config import (
    CATEGORY_VALUES,
    CONDITION_VALUES,
    DEPARTMENT_VALUES,
    LOCATION_VALUES,
    STRATA_VALUES,
)
from scraper.scraper import scrape, set_store
from shared.models import SearchParams
from shared.store import ListingStore


def _ask(prompt: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or (default or "")


def _ask_int(prompt: str, default: int) -> int:
    raw = _ask(prompt, str(default))
    try:
        return int(raw)
    except ValueError:
        return default


def _ask_bool(prompt: str, default: bool) -> bool:
    raw = _ask(f"{prompt} (y/n)", "y" if default else "n").lower()
    return raw.startswith("y")


def _menu(label: str, options: list[str], allow_skip: bool = True) -> str | None:
    print(f"\n{label}")
    if allow_skip:
        print("  0) (skip)")
    for idx, opt in enumerate(options, start=1):
        print(f"  {idx}) {opt}")
    raw = _ask("Choice", "0" if allow_skip else "1")
    try:
        n = int(raw)
    except ValueError:
        return None if allow_skip else options[0]
    if allow_skip and n == 0:
        return None
    if 1 <= n <= len(options):
        return options[n - 1]
    return None if allow_skip else options[0]


def _prompt_params() -> SearchParams:
    print("=== Grailed scraper tester ===\n")
    query = _ask("Query (free text, blank = none)", "")
    department = _menu("Department:", DEPARTMENT_VALUES)
    category = _menu("Category:", CATEGORY_VALUES)
    category_path = _ask("Category path (e.g. tops.short_sleeve_shirts, blank = none)", "")
    designer = _ask("Designer (e.g. Nike, blank = none)", "")
    condition = _menu("Condition:", CONDITION_VALUES)
    location = _menu("Location:", LOCATION_VALUES)
    strata = _menu("Strata:", STRATA_VALUES)
    min_price = _ask_int("Min price USD", 0)
    max_price = _ask_int("Max price USD", 1_000_000)
    live_limit = _ask_int("Live listings limit", 5)
    include_sold = _ask_bool("Include sold comparables?", True)
    sold_limit = _ask_int("Sold comparables per live listing", 3) if include_sold else 0
    fetch_descriptions = _ask_bool("Fetch full descriptions? (slower)", False)

    return SearchParams(
        query=query,
        department=department,
        category=category,
        category_path=category_path or None,
        designer=designer or None,
        condition=condition,
        location=location,
        strata=strata,
        min_price_usd=min_price,
        max_price_usd=max_price,
        live_limit=live_limit,
        sold_limit=sold_limit,
        include_sold=include_sold,
        fetch_descriptions=fetch_descriptions,
    )


def _print_result(result) -> None:
    print("\n=== metadata ===")
    print(json.dumps(result.metadata.model_dump(mode="json"), indent=2))
    print(f"\n=== {len(result.results)} live listing(s) ===")
    for idx, row in enumerate(result.results, start=1):
        print(f"\n--- live [{idx}/{len(result.results)}] {row.live_listing.id} ---")
        print(json.dumps(row.live_listing.model_dump(mode="json"), indent=2))
        if row.sold_comparables:
            print(f"\n    sold comparables: {len(row.sold_comparables)}")
            for jdx, sold in enumerate(row.sold_comparables, start=1):
                print(f"\n    --- sold [{jdx}/{len(row.sold_comparables)}] {sold.id} ---")
                print(json.dumps(sold.model_dump(mode="json"), indent=2))


def _wire_store() -> None:
    load_dotenv()
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env to use --persist"
        )
    from supabase import create_client

    set_store(ListingStore(create_client(url, key)))


def main(argv: list[str] | None = None) -> int:
    args = list(argv) if argv is not None else sys.argv[1:]
    persist = "--persist" in args

    if persist:
        _wire_store()

    try:
        params = _prompt_params()
    except (EOFError, KeyboardInterrupt):
        print("\naborted", file=sys.stderr)
        return 130

    print("\n=== running scrape ===")
    print(json.dumps(params.model_dump(mode="json"), indent=2))
    print(f"persist={persist}")

    result = asyncio.run(scrape(params, persist=persist))
    _print_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
