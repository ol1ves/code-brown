# Backend Orchestration Rewrite — Design Spec

**Status:** approved, pending implementation plan
**Owner:** Oliver
**Last updated:** 2026-04-26
**Branch:** `backend-rewrite` (off `backend`)
**Related:** [SPEC.md](../../SPEC.md), [EV_MODEL_SPEC.md](../../../ev/EV_MODEL_SPEC.md), [README.md](../../../README.md)

---

## 1. Summary

The current `backend/` is fragile glue. One ~333-line `orchestrator.py` mixes three concerns (search, hype, agent streaming), the agent flow doesn't produce useful results, hype's data source (Google Trends) is rate-limited and busted, errors get swallowed, and there's no structured logging anywhere. The CLI is an interactive prompt that's slow to drive and produces shallow output.

This rewrite:

1. **Deletes** the agent flow and the hype endpoint outright (no stub, no dead code) — these come back later on a separate branch with a working signal source.
2. **Reshapes** the search pipeline into named, observable stages with a single `RunContext` carrying timing/counts/warnings. Logs and CLI presentation read from the same context — one source of truth for "what happened in this run."
3. **Reconciles** with EV's current output shape (the math owner added `expected_profit_grailed`, `buy_cost`, `confidence_percentage`, etc.). Ranking switches from `p_sell * edge_usd` to `p_sell * expected_profit_grailed`. Legacy compat fields are dropped from the surface API.
4. **Adds structured logging** via stdlib `logging` with a JSON formatter. Every log line carries `run_id` + `stage`. `LOG_FORMAT=text` env var swaps to a key=value formatter for casual terminal tails.
5. **Rewrites the CLI** with positional args (`python -m backend.cli search "<query>" <live_limit> <sold_limit>`) and a packaged, sectioned presentation block.

**Hard boundary:** the rewrite touches `backend/`, `shared/models.py`, `shared/store.py` (recommendations table accessor only), `supabase/migrations/` (one new migration), and `docs/`. It does **not** touch `ev/`, `scraper/`, or `hype/` internals.

---

## 2. Scope

### In scope

- New `backend/` layout (see §4).
- Delete `backend/agent/` directory entirely (intent.py, planner.py, summary.py, llm.py, __init__.py).
- Delete `POST /agent/run` route and `run_agent_stream` from orchestrator.
- Delete `GET /hype/{term}` route and `run_hype` from orchestrator.
- Reshape `Recommendation` top-level fields to use new EV outputs; drop legacy `edge_usd`, `cost`, `confidence: str`.
- Drop agent-only models from `shared/models.py`: `AgentRunRequest`, `CandidateQuery`, `PlanPickedQuery`, `PlanSkippedQuery`, `AgentPlan`, `SummaryHighlight`, `AgentSummary`, `HypeProbeResult`, `AgentRunState`.
- Drop hype-only models from `shared/models.py`: `HypeResult`, `TrendSeries`, `TrendPoint`, `RelatedQuery`, `HypeEvidence` (no public consumer after `/hype` is removed). The `hype/` package's own internal types are unaffected.
- New Supabase migration: drop legacy columns/index, add new columns/index, replace `list_latest_recommendations` RPC.
- Update `shared/store.py:save_recommendations` to write the new column set.
- Structured JSON logging (`backend/logging_setup.py`) with `LOG_FORMAT=text` override.
- New `backend/pipeline/` with `context.py` and `search.py`.
- New `backend/presenter.py` for CLI output rendering.
- CLI rewrite (`backend/cli.py`): one subcommand `search`, positional args, no interactive prompt.
- README rewrite to match the new endpoint surface and field names.
- Archive `docs/2026-04-25-agent-run-sse-spec.md` → `docs/archive/`.
- New `docs/agent-flow-future.md` placeholder (~10 lines).

### Out of scope (hard)

- Anything inside `ev/` (no model edits, no `__init__.py` changes).
- Anything inside `scraper/` (call surface stays as-is).
- Anything inside `hype/` (the directory may stay as orphaned code or be deleted in a follow-up; this rewrite leaves it untouched on disk but unused at runtime).
- `frontend/` and `agent-ui/` — they will break (see §11). Fixing them is a follow-up task.
- Rebuilding the agent flow with a working signal source (separate future branch).
- Caching, rate-limiting, retries beyond what scraper already does.
- Run history persistence (logs only, no `runs` table).
- OpenTelemetry, hosted tracers, LLM observability tooling.

---

## 3. Architecture

```
┌─────────────────────────┐         ┌────────────────────────┐
│   backend/main.py       │         │   backend/cli.py       │
│   FastAPI: routes only  │         │   argparse: 1 subcmd   │
└────────────┬────────────┘         └──────────┬─────────────┘
             │                                  │
             │  run_search(params, ctx)         │
             ▼                                  ▼
        ┌────────────────────────────────────────────┐
        │   backend/pipeline/search.py                │
        │   run_search(params, ctx) -> SearchResult   │
        │                                             │
        │     scrape_stage(params, ctx)               │
        │       └─ scraper.scrape(params)             │
        │     value_stage(rows, ctx)                  │
        │       └─ ev.value_listing                   │
        │       └─ ev.estimate_sell_probability       │
        │     rank_stage(items, ctx)                  │
        │     persist_stage(result, params, ctx)      │
        │       └─ store.save_recommendations         │
        └─────────────┬───────────────────────────────┘
                      │
                      │ ctx.timings, ctx.counts, ctx.warnings
                      ▼
        ┌────────────────────────────────────────────┐
        │ backend/presenter.py                        │
        │ render_search_result(result, ctx) -> str   │
        │                                             │
        │   METADATA  ┃  TOP RESULTS  ┃  WARNINGS    │
        └────────────────────────────────────────────┘
```

`RunContext` is the spine: every stage logs through `ctx.logger`, records timing through `ctx.record_stage(...)`, accumulates counts and warnings on the context. The presenter and the logger both read from `ctx` — no duplicate "what happened" tracking.

Both the FastAPI route handler and the CLI build a `RunContext` and call `run_search`. The HTTP path serializes the response model (no presenter call). The CLI path passes the result + ctx to the presenter and prints the string.

---

## 4. File layout

### New files

```
backend/
  logging_setup.py              # configure_logging(level, format)
  presenter.py                  # render_search_result(result, ctx) -> str
  pipeline/
    __init__.py                 # empty
    context.py                  # RunContext dataclass
    search.py                   # run_search + private stage functions
```

### Rewritten files

- `backend/main.py` — slim down to `/health`, `POST /search`, `GET /recommendations`. No middleware changes (bearer auth stays).
- `backend/cli.py` — single subcommand, positional args.
- `shared/models.py` — `Recommendation` reshape; agent + hype model deletions.
- `shared/store.py` — `save_recommendations` writes new columns.

### Deleted files

```
backend/agent/                   # whole directory
docs/2026-04-25-agent-run-sse-spec.md  # moved to docs/archive/
```

### Empty/placeholder

- `docs/agent-flow-future.md` (~10 lines, see §10).

---

## 5. Data contracts

### 5.1 New `Recommendation` shape (`shared/models.py`)

```python
class Recommendation(BaseModel):
    """One ranked recommendation. Single shape returned by both /search and
    /recommendations.

    Top-level fields are extracted from EV outputs at construction time so the
    frontend can sort/filter/display without digging into JSONB. ``valuation``
    and ``sell_probability`` stay as opaque dicts so the math owner can add
    fields additively without API churn.
    """

    item_id: str
    scraped_at_unix: int
    query: str

    # Ranking + cost surface (new EV fields)
    expected_profit_grailed: float        # primary rank field; q50_net_payout - buy_cost
    expected_profit_off_grailed: float    # secondary; q50 - buy_cost
    buy_cost: float                       # listing + NYC tax + shipping (true acquisition cost)
    p_sell: float                         # from sell-probability model
    q50: float                             # weighted-percentile median resale price
    confidence_pct: float                  # 0-100, from EV's confidence_percentage

    # Opaque payloads
    valuation: dict
    sell_probability: dict
    live_listing: LiveListing
```

**Removed top-level fields:** `edge_usd`, `cost`, `confidence` (string). Callers that need them can read `valuation["metrics"]["edge_usd"]`, `valuation["cost"]`, etc. — the EV module still emits them as legacy compat. We just stop promoting them on the `Recommendation` surface.

### 5.2 Ranking formula

**Old:** `r.p_sell * r.edge_usd`
**New:** `r.p_sell * r.expected_profit_grailed`

Used inside `rank_stage` (in-memory sort) and inside the `list_latest_recommendations` RPC (DB sort by `expected_profit_grailed desc`).

### 5.3 Models being deleted

From `shared/models.py`:

- `AgentRunRequest`
- `CandidateQuery`
- `PlanPickedQuery`
- `PlanSkippedQuery`
- `AgentPlan`
- `SummaryHighlight`
- `AgentSummary`
- `HypeProbeResult`
- `AgentRunState`
- `HypeResult`
- `TrendSeries`
- `TrendPoint`
- `RelatedQuery`
- `HypeEvidence`

All hype-related models go because the endpoint is gone. The `hype/` directory's own internal types are unaffected — those stay.

### 5.4 Supabase migration

New file: `supabase/migrations/20260426XXXXXX_recs_use_grailed_profit.sql`

```sql
-- Drop legacy index (will be replaced)
drop index if exists public.recommendations_edge_usd_idx;

-- Add new columns
alter table public.recommendations
  add column expected_profit_grailed     numeric,
  add column expected_profit_off_grailed numeric,
  add column buy_cost                    numeric,
  add column confidence_pct              numeric;

-- Backfill from JSONB for any existing rows (best-effort; null where missing)
update public.recommendations
set expected_profit_grailed     = (valuation->'metrics'->>'expected_profit_grailed')::numeric,
    expected_profit_off_grailed = (valuation->'metrics'->>'expected_profit_off_grailed')::numeric,
    buy_cost                    = (valuation->>'buy_cost')::numeric,
    confidence_pct              = (valuation->'metrics'->>'confidence_percentage')::numeric;

-- Enforce NOT NULL going forward
alter table public.recommendations
  alter column expected_profit_grailed     set not null,
  alter column expected_profit_off_grailed set not null,
  alter column buy_cost                    set not null,
  alter column confidence_pct              set not null;

-- Drop legacy columns
alter table public.recommendations
  drop column edge_usd,
  drop column cost,
  drop column confidence;

-- New index
create index recommendations_expected_profit_grailed_idx
  on public.recommendations (expected_profit_grailed desc);

-- Replace RPC: dedupe by seller listing identity, rank by new field
create or replace function public.list_latest_recommendations(p_limit int)
returns setof public.recommendations
language sql stable as $$
  with latest as (
    select distinct on (
      live_listing->'seller'->>'seller_name',
      live_listing->>'name',
      live_listing->>'size',
      live_listing->'price'->>'listing_price_usd'
    ) *
    from public.recommendations
    order by
      live_listing->'seller'->>'seller_name',
      live_listing->>'name',
      live_listing->>'size',
      live_listing->'price'->>'listing_price_usd',
      scraped_at_unix desc,
      expected_profit_grailed desc
  )
  select * from latest
  order by expected_profit_grailed desc
  limit p_limit;
$$;
```

If the dev DB has rows where the JSONB doesn't carry the new fields (because they were inserted before EV's update), the backfill leaves NULL and the `set not null` step fails. Recovery: either delete the offending rows (`delete from recommendations where (valuation->'metrics'->>'expected_profit_grailed') is null;`) before re-running, or split the migration into two and accept nullable columns. The MVP accepts a `delete + retry` for the dev DB.

### 5.5 `shared/store.py:save_recommendations` change

Replace the row dict to write the new columns. The legacy keys are gone:

```python
rows = [
    {
        "item_id": item.item_id,
        "scraped_at_unix": item.scraped_at_unix,
        "query": item.query,
        "params": params_json,
        "expected_profit_grailed": item.expected_profit_grailed,
        "expected_profit_off_grailed": item.expected_profit_off_grailed,
        "buy_cost": item.buy_cost,
        "p_sell": item.p_sell,
        "q50": item.q50,
        "confidence_pct": item.confidence_pct,
        "valuation": item.valuation,
        "sell_probability": item.sell_probability,
        "live_listing": item.live_listing.model_dump(mode="json"),
    }
    for item in response.items
]
```

`list_recommendations` is unchanged at the Python level — it calls the RPC, which is replaced by §5.4.

---

## 6. RunContext (`backend/pipeline/context.py`)

```python
"""Per-run state passed through every pipeline stage.

Holds the run id, a pre-bound logger, and accumulating counters/timings/warnings
that the presenter and structured logs both read from. Stages mutate the context
via ``record_stage`` and ``add_warning`` — no other state lives outside.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from time import monotonic


@dataclass
class RunContext:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    started_at: float = field(default_factory=monotonic)
    timings_ms: dict[str, int] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    logger: logging.Logger = field(init=False)

    def __post_init__(self) -> None:
        self.logger = logging.LoggerAdapter(
            logging.getLogger("backend"),
            {"run_id": self.run_id},
        )

    def record_stage(self, stage: str, duration_ms: int, **counts: int) -> None:
        self.timings_ms[stage] = duration_ms
        for key, value in counts.items():
            self.counts[f"{stage}.{key}"] = value

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def total_ms(self) -> int:
        return int((monotonic() - self.started_at) * 1000)
```

The `LoggerAdapter` ensures every log line emitted via `ctx.logger` carries `run_id` in its `extra` automatically. Stages emit log lines with additional structured fields via the `extra=` kwarg — the JSON formatter (§7) merges them.

---

## 7. Logging (`backend/logging_setup.py`)

```python
"""Configure root logger. Call once from main.py:lifespan and cli.py:main.

Default: JSON-line formatter (one object per line). Set LOG_FORMAT=text for
key=value formatting in casual terminal tails.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime

_RESERVED = {
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "message", "taskName",
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class KeyValueFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(tz=UTC).isoformat()
        base = f"{ts} {record.levelname:5s} {record.name}"
        extras = " ".join(
            f"{k}={v}"
            for k, v in record.__dict__.items()
            if k not in _RESERVED and not k.startswith("_")
        )
        msg = record.getMessage()
        line = f"{base}  {extras}  msg={msg!r}".strip()
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str = "INFO") -> None:
    fmt = os.environ.get("LOG_FORMAT", "json").lower()
    formatter = JsonFormatter() if fmt == "json" else KeyValueFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
```

Called from:
- `main.py:lifespan` startup
- `cli.py:main` entry

No log calls happen before `configure_logging`.

---

## 8. Pipeline (`backend/pipeline/search.py`)

Single file. Stages are private functions (`_scrape_stage`, `_value_stage`, `_rank_stage`, `_persist_stage`). One public function: `run_search`.

### Stage signatures

```python
async def run_search(params: SearchParams, ctx: RunContext, *, persist: bool = True) -> SearchResponse: ...

async def _scrape_stage(params: SearchParams, ctx: RunContext) -> GrailedScrapeResult: ...

def _value_stage(scrape_result: GrailedScrapeResult, params: SearchParams, ctx: RunContext) -> list[Recommendation]: ...

def _rank_stage(items: list[Recommendation], ctx: RunContext) -> list[Recommendation]: ...

def _persist_stage(response: SearchResponse, params: SearchParams, ctx: RunContext) -> None: ...
```

### Stage contracts

Every stage:
1. Calls `ctx.logger.info("stage_started", extra={"stage": <name>})` on entry.
2. Records start time via `monotonic()`.
3. Runs its logic. Catches no exceptions — bugs propagate. `_value_stage` and `_persist_stage` may add warnings via `ctx.add_warning(...)` for soft failures (no_data rows, persistence skipped).
4. Calls `ctx.record_stage(<name>, duration_ms, **counts)` with stage-specific count keys.
5. Calls `ctx.logger.info("stage_completed", extra={"stage": <name>, "duration_ms": ..., **counts})`.

### Per-stage count keys (for §9 presenter)

- `scrape`: `live_requested`, `live_returned`, `total_live_found` (from scrape metadata)
- `value`: `valued`, `no_data`, `errored`, `sold_comps_total`, `sold_comps_with_data`
- `rank`: `ranked` (final count after sort, equals `valued`)
- `persist`: `inserted` (rows written) — `0` if `persist=False` or store unavailable

### `run_search` body (sketch)

```python
async def run_search(params: SearchParams, ctx: RunContext, *, persist: bool = True) -> SearchResponse:
    ctx.logger.info("run_started", extra={"query": params.query, "live_limit": params.live_limit, "sold_limit": params.sold_limit})

    scrape_result = await _scrape_stage(params, ctx)
    items = _value_stage(scrape_result, params, ctx)
    ranked = _rank_stage(items, ctx)
    response = SearchResponse(metadata=scrape_result.metadata, items=ranked)

    if persist:
        _persist_stage(response, params, ctx)

    ctx.logger.info("run_completed", extra={"total_ms": ctx.total_ms, **ctx.counts})
    return response
```

### `_value_stage` no_data handling

`Recommendation` no longer carries the `no_data` synthetic items from the old `surface_no_data=True` path. Reasoning: that flag existed only for the agent UI to show live listings without comp data. Agent flow is gone, so `_value_stage` simply drops `no_data` rows and increments `ctx.counts["value.no_data"]`. Each dropped row also adds a warning: `f"no_data: {item_id} ({designer} {name})"`.

### Error semantics

- Scraper exceptions propagate. `_scrape_stage` does not catch.
- EV exceptions on a single row are caught per-row, logged at `WARNING` level with the item_id, counted in `ctx.counts["value.errored"]`, and the row is dropped. Reason: one bad row shouldn't kill the whole run.
- Persistence failures are caught and logged at `ERROR`; they add a warning. The response is still returned to the caller. Reason: persistence is a side effect; the user already paid the scrape cost.

---

## 9. Presenter (`backend/presenter.py`)

One public function:

```python
def render_search_result(response: SearchResponse, ctx: RunContext, *, top_n: int = 20) -> str: ...
```

Output is a single string with three sections separated by horizontal rules. ANSI colors are emitted only when `sys.stdout.isatty()`. `--no-color` CLI flag forces them off.

### Layout

```
═══════════════════════════════════════════════════════════════════════════════
  SEARCH  query="margiela gats"  run_id=a1b2c3d4e5f6  total=8.4s
═══════════════════════════════════════════════════════════════════════════════

  STAGE TIMINGS                       LISTING FUNNEL
  ─────────────────────────           ────────────────────────────
  scrape       6,213 ms               live requested      40
  value         1,940 ms               live returned       38
  rank             4 ms               valued              22
  persist        251 ms               no_data             14
                                       errored              2
  total        8,408 ms

  COMP FUNNEL
  ─────────────────────────
  sold comps total        912
  sold comps with data    634   (69.5%)


───────────────────────────────────────────────────────────────────────────────
  TOP 20 RESULTS  ranked by p_sell × expected_profit_grailed
───────────────────────────────────────────────────────────────────────────────

  #   designer / name                       buy    q50    profit  off    p_sell  conf  comps
  ─── ──────────────────────────────────── ────── ────── ─────── ────── ─────── ───── ─────
   1  Maison Margiela / Replica GAT 42    $189   $342   $122    $153   0.71    78%   12/14
   2  Maison Margiela / Replica GAT 41    $204   $342   $107    $138   0.62    78%   12/14
  ...

───────────────────────────────────────────────────────────────────────────────
  WARNINGS  (14)
───────────────────────────────────────────────────────────────────────────────

  no_data  abc123  Maison Margiela / Tabi Boot 41
  no_data  def456  Maison Margiela / Replica GAT 38
  ...
  (8 more — pass --json for full list)

═══════════════════════════════════════════════════════════════════════════════
```

### Formatting rules

- All money values right-aligned, dollar sign included, no decimals (rounded to nearest dollar in display only — the underlying floats remain).
- Percentages right-aligned, integer percent with `%` suffix.
- Designer/name truncated to fit column width (~36 chars), ellipsis if longer.
- Confidence: integer percent. Optional color hint: ≥75 green, 50-74 yellow, <50 red. Only on TTY.
- Profit columns: green if positive, red if negative. Only on TTY.
- Comps column: `valid_time/total` — i.e. `12/14` means 14 sold comps were retrieved, 12 had usable timestamps.
- Warnings section: cap at 6 lines visible; if more, append `(N more — pass --json for full list)`.

### `--json` mode

CLI flag `--json` skips the presenter entirely and dumps `response.model_dump_json(indent=2)`. The metrics block is omitted from JSON output (it's diagnostic, not contract). If you need ctx data programmatically, that's a follow-up.

---

## 10. CLI (`backend/cli.py`)

### Usage

```
python -m backend.cli search <query> <live_limit> <sold_limit> [--no-persist] [--json] [--no-color]
```

Examples:

```
python -m backend.cli search "margiela gats" 40 40
python -m backend.cli search guidi 20 30 --no-persist
python -m backend.cli search "carol christian poell" 10 10 --json | jq
```

### Behavior

- All three positional args required. `query` is a single string (quote it for multi-word).
- `live_limit` and `sold_limit` must be positive integers; argparse `type=int` handles validation.
- All other `SearchParams` fields use Pydantic defaults (no department, no condition, no price filter, etc.). Filters live in the API request body, not the CLI surface — the CLI is for fast manual sanity checks.
- `--no-persist` — pass `persist=False` to `run_search`. Skips Supabase wiring.
- `--json` — dump JSON instead of presenter output.
- `--no-color` — disable ANSI color in presenter output.

### Code structure

```python
def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command != "search":
        # argparse with required=True makes this unreachable; defensive return
        return 1

    configure_logging(level="INFO")
    if not args.no_persist:
        _wire_stores()

    params = SearchParams(query=args.query, live_limit=args.live_limit, sold_limit=args.sold_limit)
    ctx = RunContext()
    response = asyncio.run(run_search(params, ctx, persist=not args.no_persist))

    if args.json:
        print(response.model_dump_json(indent=2))
    else:
        print(render_search_result(response, ctx))
    return 0
```

`_wire_stores()` is the same helper that already exists, lifted as-is.

### Exit codes

- `0` — success
- `1` — uncaught exception (printed to stderr by top-level `try/except`)
- `2` — argparse usage error (default argparse behavior)

---

## 11. FastAPI surface (`backend/main.py`)

Three routes after the rewrite:

| Route                  | Method | Auth   | Notes                                |
|------------------------|--------|--------|--------------------------------------|
| `/health`              | GET    | public | unchanged                            |
| `/search`              | POST   | bearer | calls `run_search`, returns `SearchResponse`, no presenter |
| `/recommendations`     | GET    | bearer | unchanged behavior, new column reads via RPC               |

`/health` HEAD also stays.

### Response handler shape

```python
@app.post("/search", response_model=SearchResponse)
async def search(params: SearchParams) -> SearchResponse:
    ctx = RunContext()
    return await run_search(params, ctx)
```

The HTTP response is the `SearchResponse` model. The CTX timings/counts are not in the HTTP response — they live in logs only. (If a future client wants them, we add a wrapper response shape; we don't bake it in pre-emptively.)

### Lifespan changes

- Call `configure_logging()` at the top of `lifespan`.
- The `set_ev_store` and `set_scraper_store` calls **stay** because EV and scraper modules use them to read prior listings — we don't touch their internals (hard boundary). `set_recommendations_store` also stays.
- Remove the `set_recommendations_store(None)` cleanup in `finally` — it's harmless but the unwire-on-shutdown pattern is overkill for a process-bound singleton. Keep if trivial; it is, so leave it.

### Routes deleted

- `POST /agent/run` and the `_sse` generator inside `main.py`.
- `GET /hype/{term}`.

---

## 12. Documentation updates

### 12.1 README rewrite

Whole file is rewritten to match the new surface. Key changes:

- §1 "Quick start" — unchanged commands, but mention `LOG_FORMAT=text` for human-readable logs.
- §2 "Environment" — drop `HYPE_TRENDS_TIMEFRAME`, `HYPE_TRENDS_GEO` rows. Drop `ALGOLIA_API_KEY` row only if it's truly unused now (verify; scraper still needs it). Keep otherwise.
- §3 "API reference" — drop the `/hype` and (already absent) `/agent/run` sections. Re-document `/search` and `/recommendations` with new field names.
- §4 "The Recommendation shape" — rewrite with new top-level fields. Drop `edge_usd`, `cost`, `confidence`. Add `expected_profit_grailed`, `expected_profit_off_grailed`, `buy_cost`, `confidence_pct`. Update the "render rule" — additive evolution still applies for the opaque dicts.
- §5 "What's stable, what's not" — pipeline is now stable; agent flow is removed; hype is removed.
- §7 "CLI harness" — rewrite with the new positional-args form and the example presentation block.

### 12.2 Doc archive

Move `docs/2026-04-25-agent-run-sse-spec.md` → `docs/archive/2026-04-25-agent-run-sse-spec.md`. Add a one-line header note: `Archived 2026-04-26 with backend orchestration rewrite. Agent flow removed; new design pending.`

### 12.3 Placeholder

New file `docs/agent-flow-future.md`:

```markdown
# Agent Flow — Future Work

The previous agent flow (`POST /agent/run`) was removed on 2026-04-26 with the
backend orchestration rewrite. Reasons:

- Hype's signal source (Google Trends) was rate-limited and producing empty
  curves on most queries, defeating the candidate-ranking step.
- The intent → candidates → hype probe → planner → search fan-out → summary
  pipeline produced mediocre results on every run we tried.
- The streaming SSE event model accumulated stage-specific shapes (10+ event
  types) that no client was using fully.

**The rebuild lives on a future branch.** Likely shape:

- Single-query agent first (intent → one good `SearchParams` → `run_search`).
- Fan-out reintroduced only when a working signal source is wired (Twitter,
  sales velocity, etc.).
- SSE event model reduced to 3-4 types: `stage_started`, `stage_completed`,
  `result`, `done`.

Archived design: [docs/archive/2026-04-25-agent-run-sse-spec.md](archive/2026-04-25-agent-run-sse-spec.md).
```

### 12.4 Update `docs/2026-04-25-rest-api-and-ev-persistence-design.md`

Add a header banner: `**Status:** partially superseded by [2026-04-26 backend orchestration rewrite](superpowers/specs/2026-04-26-backend-orchestration-rewrite-design.md). Field names (edge_usd, cost, confidence) changed.`

Don't fully rewrite — it's a historical record.

---

## 13. Testing

### 13.1 Unit tests (`tests/test_pipeline_search.py`)

- `test_run_search_drops_no_data_rows` — patch scraper + `value_listing` so first row is no_data, second is valid; assert only second appears in result.
- `test_run_search_sorts_by_p_sell_times_expected_profit_grailed` — patch with three rows whose `expected_profit_grailed`/`p_sell` products are 5, 50, 20; assert order [50, 20, 5].
- `test_run_search_records_stage_timings` — assert `ctx.timings_ms` has keys `scrape`, `value`, `rank`, `persist`.
- `test_run_search_records_counts` — assert `ctx.counts` contains expected `scrape.live_returned`, `value.valued`, `value.no_data`, etc.
- `test_run_search_persist_false_skips_persist_stage` — assert no `persist` key in timings, no `_persist_stage` call.
- `test_value_stage_per_row_exception_drops_row_and_counts_errored` — patch `value_listing` to raise on one row; assert that row dropped, `ctx.counts["value.errored"] == 1`.

### 13.2 Logging tests (`tests/test_logging_setup.py`)

- `test_json_formatter_emits_required_fields` — capture log output; assert one JSON object per line with `ts`, `level`, `logger`, `msg`, plus any `extra` fields merged.
- `test_text_formatter_emits_key_value_pairs` — set `LOG_FORMAT=text`; assert grep-ability of `run_id=...`.
- `test_run_context_logger_binds_run_id` — emit a log via `ctx.logger`; assert the parsed JSON line contains the `run_id`.

### 13.3 Presenter tests (`tests/test_presenter.py`)

- `test_render_includes_all_three_sections` — assert "STAGE TIMINGS", "TOP", "WARNINGS" headers in output.
- `test_render_truncates_warnings_section` — feed 20 warnings; assert "(14 more" line present.
- `test_render_no_color_when_not_tty` — capture output with `sys.stdout.isatty()` patched False; assert no ANSI escapes.
- `test_render_top_n_caps_at_arg` — feed 50 results; assert exactly 20 in output (default).

### 13.4 CLI smoke tests (`tests/test_cli.py`)

- `test_search_subcommand_invokes_run_search` — patch `run_search` to return a fixed response; assert called with `params.query="margiela gats"`, `live_limit=40`, `sold_limit=40`.
- `test_search_subcommand_json_flag_emits_valid_json` — patch, run with `--json`; assert stdout parses, has top-level `metadata` and `items`.
- `test_search_subcommand_no_persist_skips_store_wiring` — patch `_wire_stores`; assert not called when `--no-persist` is given.

### 13.5 Migration test

Manual only. After applying the migration:
1. `select column_name from information_schema.columns where table_name='recommendations'` — verify new columns exist, legacy gone.
2. Run `select * from list_latest_recommendations(5)` — verify it returns rows ordered by `expected_profit_grailed desc`.

### 13.6 No tests against real Grailed/EV/Algolia from CI

Existing convention; preserved.

---

## 14. Manual integration check (run before merging)

1. `cd` to repo root, activate venv, ensure `.env` populated.
2. Apply the new migration to dev Supabase (`supabase db push` or paste into SQL editor).
3. `python -m backend.cli search "margiela gats" 10 10` — expect a presenter block with three sections, total time 8-30s.
4. `python -m backend.cli search guidi 5 5 --no-persist --json | jq` — expect valid JSON; `items` array; each item has new top-level fields (`expected_profit_grailed`, `buy_cost`, `confidence_pct`); no `edge_usd`/`cost`/`confidence` keys at top level.
5. `LOG_FORMAT=text python -m backend.cli search guidi 5 5` — expect human-readable log lines on stderr (or stdout, depending on handler) with `run_id=...`.
6. `uvicorn backend.main:app --reload --port 8000`, then:
   ```
   curl -X POST http://localhost:8000/search \
     -H "Authorization: Bearer $API_KEY" \
     -H "content-type: application/json" \
     -d '{"query":"guidi","live_limit":3,"sold_limit":5}'
   ```
   Expect 200 with new field names. Curl `GET /recommendations?limit=10` — expect new fields. `GET /hype/guidi` and `POST /agent/run` should return 404.
7. Confirm no JSON log line carries an unhandled exception unless intentional.

---

## 15. Known impact on existing UIs (out-of-scope, but documented)

- `agent-ui/` calls `POST /agent/run`. After this rewrite, that endpoint returns 404. **`agent-ui/` will not function.** Fixing it (or deleting it) is a follow-up.
- `frontend/app/api/recommendations/route.ts` reads `edge_usd`, `cost`, `confidence` per [frontend/app/page.tsx](../../../frontend/app/page.tsx). Those fields are gone from the top-level Recommendation shape. **`frontend/` will render broken cards** until updated to use `expected_profit_grailed`, `buy_cost`, `confidence_pct`.
- `frontend/app/api/hype/[term]/route.ts` proxies to `/hype`. After rewrite that endpoint is 404. **`frontend/` hype panel will fail.**

These are documented for the team; the rewrite intentionally does not patch them. A follow-up task picks them up. The README §11 (this section) calls this out.

---

## 16. Decisions locked

| Decision | Resolution |
|---|---|
| Agent flow | Delete entirely; placeholder note + archive doc. Rebuild on future branch. |
| Hype endpoint | Delete entirely. Source was busted. Future signal source likely Twitter. |
| Observability | Stdlib `logging`, JSON formatter default, `LOG_FORMAT=text` override. No DB run history. |
| EV reconciliation | Adopt new fields (`expected_profit_grailed`, `buy_cost`, `confidence_pct`). Drop legacy from top-level Recommendation. |
| Ranking formula | `p_sell × expected_profit_grailed`, both in-memory and in RPC. |
| Supabase migration | Add new columns, drop legacy, replace RPC. Single migration file. |
| CLI shape | `python -m backend.cli search "<query>" <live_limit> <sold_limit>` — positional, no interactive prompt. |
| Presenter | Three sections (METADATA / TOP / WARNINGS), TTY-detected ANSI color, `--no-color` flag, `--json` bypass. |
| Architecture | Approach 2 — pipeline stages with shared `RunContext`. Restrained file count. |
| Branch | `backend-rewrite` off current `backend`. |
| UIs | Will break; follow-up task. Not in this rewrite's scope. |

---

## 17. Open items

None. All decisions locked in conversation 2026-04-26.
