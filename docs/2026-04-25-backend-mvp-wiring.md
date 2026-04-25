# Backend MVP Wiring — Design Spec

**Status:** approved, pending implementation
**Owner:** Oliver
**Last updated:** 2026-04-25
**Related:** [SPEC.md](SPEC.md), [docs/2026-04-24-grailed-scraper-design.md](2026-04-24-grailed-scraper-design.md), [ev/EV_MODEL_SPEC.md](../ev/EV_MODEL_SPEC.md), [docs/2026-04-24-hype-score-trends-native-design.md](2026-04-24-hype-score-trends-native-design.md)

---

## 1. Summary

Wire the merged modules (`scraper/`, `ev/`, `hype/`) into a minimal backend MVP that produces ranked arbitrage results and hype scores. Test it with a CLI before any FastAPI handlers exist. The CLI is a **test harness only** — all wiring lives in `backend/orchestrator.py` so the eventual API handlers are one-line wrappers.

Two independent flows, decoupled from day one:

1. **Search** — `SearchParams → SearchResponse` (scrape + EV + sell-probability + rank).
2. **Hype** — `term → HypeResult` (Google Trends-native, parallel ranges + related queries).

No shared state. No coupling between the two. Same input vocabulary (a search term lives in both) but the orchestrator does not call hype from search or vice versa. This mirrors the eventual frontend pattern where `/search` and `/hype` are two parallel HTTP requests.

---

## 2. Scope

**In scope:**
- `ev/__init__.py` shim that re-exports `value_listing`, `estimate_sell_probability`, `process_scrape` so callers can `from ev import …` despite the spaces in the model filenames. (**Already landed in this branch.**)
- New `backend/orchestrator.py` with two pure async functions: `run_search`, `run_hype`.
- New result contracts in `shared/models.py`: `RankedListing`, `SearchResponse`.
- New `backend/cli.py` test harness with two subcommands: `search` and `hype`.
- No FastAPI handlers yet; `backend/main.py` stays as-is.

**Out of scope:**
- `/search` and `/hype` HTTP endpoints. The orchestrator functions exist to be wrapped later — wrapping is one line each and is deferred until the orchestrator is exercised end-to-end via CLI.
- Persistence. `scraper.scrape(persist=False)` only. Supabase is not required to run the CLI.
- QC, image scoring, description LLM. Not merged, not wired.
- Caching. Hype rate-limit budget is left exactly as the existing CLI uses it.
- Modifications to `scraper/`, `hype/`, or the two `ev/` model files. We only add the ev shim and new wiring code; nothing else moves.

---

## 3. Architecture

```
                   ┌────────────────────────────────────────┐
                   │             backend/cli.py              │
                   │   subcommands: search | hype            │
                   │   (test harness — no business logic)    │
                   └─────────────┬──────────────┬────────────┘
                                 │              │
                                 ▼              ▼
                ┌────────────────────────────────────────────┐
                │           backend/orchestrator.py           │
                │                                            │
                │   async run_search(params) -> SearchResp   │
                │   async run_hype(term)     -> HypeResult   │
                └────┬────────────────────────────┬──────────┘
                     │                            │
   ┌─────────────────┴───────────────┐    ┌───────┴──────────┐
   │            search flow           │    │    hype flow      │
   │                                  │    │                   │
   │  scraper.scrape(params,          │    │  asyncio.gather(  │
   │                  persist=False)  │    │    to_thread(     │
   │            │                     │    │      trends.fetch │
   │            ▼                     │    │      30d/7d/90d), │
   │  for row in result.results:      │    │    to_thread(     │
   │    ev.value_listing(row, t)      │    │      related.fetch│
   │    ev.estimate_sell_probability  │    │  )                │
   │            │                     │    │            │       │
   │            ▼                     │    │            ▼       │
   │  drop no_data, sort by edge_usd  │    │  score.compute(    │
   │            │                     │    │      30d.points)   │
   │            ▼                     │    │            │       │
   │       SearchResponse             │    │      HypeResult    │
   └──────────────────────────────────┘    └───────────────────┘
```

Both flows are driven by `asyncio.run` from the CLI. Neither flow imports from the other.

---

## 4. Data contracts — `shared/models.py`

**Add** to `shared/models.py` (do not modify existing classes):

```python
class RankedListing(BaseModel):
    """One ranked search result: the live listing plus all model outputs.

    ``valuation`` and ``sell_probability`` are kept as ``dict`` rather than
    typed models because:
      - The two EV model files emit raw dicts, not pydantic instances.
      - ``valuation`` has two distinct shapes (success vs ``{"status": "no_data"}``)
        and the ranker drops no_data rows, but we want flexibility to evolve the
        success shape without churning the contract here.
    Both dicts are passed through unchanged, so the EV spec is the source of truth.
    """

    live_listing: LiveListing
    sold_comparables: list[SoldListing] = Field(default_factory=list)
    valuation: dict
    sell_probability: dict


class SearchResponse(BaseModel):
    """Full ranked search response. Returned by ``orchestrator.run_search``."""

    metadata: ScrapeMetadata
    ranked: list[RankedListing] = Field(default_factory=list)
```

`HypeResult` already exists and is used as-is for the hype flow.

---

## 5. `backend/orchestrator.py` — full spec

Pure async functions. No FastAPI imports. No CLI imports. No prints. Importable from anywhere.

```python
"""Wires the merged modules into two independent flows.

run_search: SearchParams -> SearchResponse  (scrape + EV + rank)
run_hype:   str          -> HypeResult      (Google Trends-native)

Both are pure orchestration. No I/O beyond what the underlying modules do.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from ev import estimate_sell_probability, value_listing
from hype import related, score, trends
from scraper.scraper import scrape
from shared.models import (
    HypeEvidence,
    HypeResult,
    RankedListing,
    SearchParams,
    SearchResponse,
)


async def run_search(params: SearchParams) -> SearchResponse:
    """Scrape, value, score, and rank. No persistence."""
    scrape_result = await scrape(params, persist=False)
    scraped_at = scrape_result.metadata.scraped_at_unix

    ranked: list[RankedListing] = []
    for row in scrape_result.results:
        row_dict = row.model_dump(mode="json")
        valuation = value_listing(row_dict, scraped_at)
        if valuation.get("status") == "no_data":
            continue
        sell_prob = estimate_sell_probability(row_dict)
        ranked.append(
            RankedListing(
                live_listing=row.live_listing,
                sold_comparables=row.sold_comparables,
                valuation=valuation,
                sell_probability=sell_prob,
            )
        )

    ranked.sort(key=lambda r: r.valuation["metrics"]["edge_usd"], reverse=True)

    return SearchResponse(metadata=scrape_result.metadata, ranked=ranked)


async def run_hype(term: str) -> HypeResult:
    """Fetch 30d/7d/90d series + related queries in parallel, compute score."""
    series_30d, series_7d, series_90d, related_items = await asyncio.gather(
        asyncio.to_thread(trends.fetch, term, "30d"),
        asyncio.to_thread(trends.fetch, term, "7d"),
        asyncio.to_thread(trends.fetch, term, "90d"),
        asyncio.to_thread(related.fetch, term),
    )

    score_value, confidence = score.compute(series_30d.points)

    return HypeResult(
        term=term,
        score=score_value,
        confidence=confidence,
        series_30d=series_30d,
        series_7d=series_7d,
        series_90d=series_90d,
        evidence=HypeEvidence(related=related_items),
        fetched_at_unix=int(datetime.now(tz=UTC).timestamp()),
    )
```

### 5.1 Behaviors locked here

- **Ranking** is deliberately the simplest thing: sort by `valuation.metrics.edge_usd` desc. Display every metric the EV models produce, but rank by one number. Future ranking changes (multiply by `p_sell`, blend hype, etc.) are a one-line change isolated to `run_search`.
- **`no_data` handling**: rows where `value_listing` returns `{"status": "no_data"}` are dropped before sorting. They never reach the response. (User decision; documented for future readers because it's not obvious from the EV spec which says only "needs handling downstream.")
- **EV input shape**: `row.model_dump(mode="json")` produces the dict the EV models expect (see [ev/EV_MODEL_SPEC.md §2](../ev/EV_MODEL_SPEC.md)). The pydantic models in `shared/models.py` already match this shape; no translation layer needed.
- **Hype parallelism**: all four pytrends calls fan out via `asyncio.to_thread` so a sync CLI can drive an async orchestrator without manual thread management. Note this is a behavior change vs. [hype/cli.py:69-75](../hype/cli.py:69) which fetches sequentially. Same calls, fewer wall-clock seconds.
- **Hype failure mode**: `asyncio.gather` with default settings raises on the first failure. The orchestrator does **not** catch exceptions from `hype/`. This matches Option A's premise: hype is independent, so a hype failure should fail the hype request, not silently degrade. The CLI catches at the top level and prints the error.
- **Scraper failure mode**: same — orchestrator does not catch. `GrailedRateLimitExceeded` and friends propagate to the CLI's top-level error handler.

### 5.2 Things explicitly NOT in the orchestrator

- No fall-back rank when EV is `no_data` for every row — `ranked` may be empty; that's a valid response.
- No top-N truncation. Caller decides how much to show. CLI shows all of them.
- No designer extraction or query-rewriting for hype. `term` is whatever the caller passes in.
- No `set_store` calls. The orchestrator is store-agnostic. Persistence is a separate concern wired in `backend/main.py` lifespan when the API lands.

---

## 6. `backend/cli.py` — test harness spec

Two subcommands. No business logic. Each subcommand assembles input, calls the orchestrator, prints the response.

```python
"""CLI test harness for the backend orchestrator.

  python -m backend.cli search        # interactive SearchParams prompt
  python -m backend.cli hype <term>   # one-shot hype lookup

This file contains zero business logic. It exists to drive
``backend.orchestrator`` from a terminal so we can verify wiring before
any HTTP handlers are written.
"""
```

### 6.1 `search` subcommand

- Reuse the existing prompt helpers from `scraper/cli.py` (`_ask`, `_ask_int`, `_ask_bool`, `_menu`, `_prompt_params`). Import them rather than duplicate. If their underscore-prefixed names feel wrong to import, lift them into a small shared `scraper/cli_prompts.py` module — but only if needed; for the MVP, importing through the underscore is fine. Test harnesses are allowed to reach.
- Call `orchestrator.run_search(params)` via `asyncio.run`.
- Print:
  1. The metadata block.
  2. For each ranked listing, in order:
     - Header line: `[N/M] <designer> <name>  (id=<id>)  url=<url>`
     - Cost / valuation line: `cost=$X  q10=$Y  q50=$Z  q90=$W  edge=$E (E%)  confidence=<level>  effective_n=<n>`
     - Sell-probability line: `p_sell=<p>  median_days=<m>  adjusted_days=<a>  pricing_ratio=<r>  comps=<num_valid_time_comps>/<num_sold_comps>`
  3. If `ranked` is empty, print one line: `no rankable listings (all comp searches returned no_data)`.

The display intentionally surfaces every field both EV models emit. Don't hide anything — this is an inspection tool.

A `--json` flag dumps `response.model_dump_json(indent=2)` instead of the human format. Useful for piping into `jq` or fixture capture.

### 6.2 `hype` subcommand

- Reuses logic identical to [hype/cli.py](../hype/cli.py) — same sparkline rendering, same summary block, same `--json` flag — but calls `orchestrator.run_hype(term)` instead of inlining the fetches.
- The point: prove the orchestrator's `run_hype` produces a `HypeResult` indistinguishable from what `hype/cli.py` produces today. If you diff the two outputs for the same term, only the `fetched_at_unix` field should differ.
- We are **not deleting** `hype/cli.py`. It stays as the standalone hype harness. `backend/cli.py hype` is the integration check that the orchestrator path works.

### 6.3 Argparse layout

```
backend.cli
  ├── search [--json]
  └── hype <term> [--json]
```

Top-level `argparse` with subparsers. Both subcommands share `--json`. Subcommand selection is required; bare `python -m backend.cli` prints help.

### 6.4 Exit codes

- `0` — success
- `1` — uncaught exception from the orchestrator (printed to stderr via top-level `try/except`)
- `130` — KeyboardInterrupt during the interactive `search` prompt

---

## 7. File-level changes

**Create:**
- `backend/orchestrator.py` — per §5.
- `backend/cli.py` — per §6.

**Modify:**
- `shared/models.py` — append `RankedListing` and `SearchResponse` (per §4). No existing classes touched.

**Already done in this branch:**
- `ev/__init__.py` — shim that re-exports `value_listing`, `estimate_sell_probability`, `process_scrape`. Verified by running `tests/test_ev_percentile_contract.py` (4 passed).

**Do NOT touch:**
- `scraper/` (Tyler's module)
- `hype/trends.py`, `hype/related.py`, `hype/score.py`, `hype/cli.py`
- `ev/percentile calc v1.py`, `ev/sell probablity model.py`, `ev/ev.py`, `ev/EV_MODEL_SPEC.md`
- `backend/main.py`
- `shared/store.py`
- The Supabase migration

---

## 8. Testing

### 8.1 Unit tests (CI-safe, no network)

Create `tests/test_orchestrator.py`:

- `test_run_search_drops_no_data_rows` — patch `scraper.scrape` and `value_listing` so the first row returns `{"status": "no_data"}` and the second returns a valid valuation; assert only the second row appears in `ranked`.
- `test_run_search_sorts_by_edge_usd_desc` — patch with three rows whose `edge_usd` values are `5, 50, 20`; assert order is `[50, 20, 5]`.
- `test_run_search_passes_persist_false_to_scraper` — assert the scraper was called with `persist=False`.
- `test_run_search_returns_empty_ranked_when_all_no_data` — assert `ranked == []` and metadata still present.
- `test_run_hype_calls_each_fetch_once_and_assembles_result` — patch `trends.fetch`, `related.fetch`, `score.compute`; assert `HypeResult` fields populated correctly and `score.compute` was called with the 30d points.

### 8.2 CLI smoke tests

Create `tests/test_backend_cli_smoke.py`:

- `test_search_subcommand_invokes_orchestrator` — patch `orchestrator.run_search` to return a fixed `SearchResponse`, monkeypatch `sys.argv` and the prompt helpers, assert stdout contains the expected header strings.
- `test_hype_subcommand_invokes_orchestrator` — patch `orchestrator.run_hype`; assert stdout contains `term=` and `score=` (parity check with `hype/cli.py`'s smoke test).
- `test_search_subcommand_json_flag_produces_valid_json` — patch the orchestrator, run with `--json`, assert stdout parses and has top-level `metadata` and `ranked` keys.

No tests against real Grailed or real pytrends from CI. Manual smoke is the integration validation (§9).

### 8.3 Pytest config

`pyproject.toml` currently sets `testpaths = ["scraper/tests"]`. Add `"tests"` to that list so the new tests run via plain `pytest`.

---

## 9. Manual integration check (run before claiming this MVP works)

1. `cd` to repo root, activate `backend/.venv`.
2. `python -m backend.cli hype "guidi"` — expect a printed `HypeResult` summary in 3-15 seconds (pytrends latency). Score may be `None` if Trends data is sparse; that's fine.
3. `python -m backend.cli search` — answer the interactive prompts with a small query (e.g. `query="guidi"`, `live_limit=3`, `sold_limit=5`). Expect a ranked list printed in 5-30 seconds. If all rows show as no_data, increase `sold_limit` and try again.
4. `python -m backend.cli search --json | python3 -m json.tool > /dev/null` — confirm JSON output round-trips.

If any step fails, the bug is in the orchestrator wiring, not in the underlying modules — the unit tests in §8 prove the modules work in isolation.

---

## 10. Future work (deferred, out of scope for this MVP)

- FastAPI handlers wrapping `run_search` and `run_hype` as `/search` and `/hype` endpoints. Both will be ~5 lines each. Bearer auth from `backend/main.py` already covers them.
- Persist toggle on `run_search` (currently hardcoded `persist=False`). When the API lands, make this an arg.
- Top-N truncation in `run_search`.
- Better ranking: `edge_usd * p_sell`, hype-weighted blend, confidence-weighted floor.
- Hype-per-designer for results (requires caching, see [docs/2026-04-24-hype-score-trends-native-design.md §13](2026-04-24-hype-score-trends-native-design.md)).
- Replace `RankedListing.valuation: dict` and `sell_probability: dict` with typed pydantic models once the EV models stabilize their no_data branch.
- Frontend coordination of `/search` + `/hype` parallel requests.
- QC integration as a post-rank filter (per [SPEC.md §3.5](SPEC.md)).

---

## 11. Open items

None. All decisions locked in conversation 2026-04-25:

| Decision | Resolution |
|---|---|
| EV import shim | Done. `ev/__init__.py` shim, verified. |
| `no_data` handling | Drop from ranking. |
| Persistence in MVP | None. `persist=False` hardcoded. |
| Hype scope | Option A — separate orchestrator function, separate CLI subcommand, no coupling to search. |
| Async/sync boundary for hype | `asyncio.to_thread` per pytrends call, fanned out via `gather`. |
| Ranking function | Sort by `valuation.metrics.edge_usd` desc. Display all metrics. |
