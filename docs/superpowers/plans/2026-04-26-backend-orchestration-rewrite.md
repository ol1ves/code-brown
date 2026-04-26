# Backend Orchestration Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `backend/` into a thin, observable search pipeline with structured logging and a packaged CLI presenter; delete the agent flow and `/hype` endpoint; reconcile `Recommendation` with EV's new output shape (`expected_profit_grailed`, `buy_cost`, `confidence_pct`).

**Architecture:** Approach 2 from the design — a `backend/pipeline/` directory with a `RunContext` dataclass that flows through named stages (`scrape → value → rank → persist`). Each stage logs entry/exit/timing/counts via stdlib `logging` (JSON formatter, with `LOG_FORMAT=text` override). FastAPI route handlers and the CLI both build a `RunContext` and call `run_search`. CLI additionally hands the result + ctx to a dedicated `presenter.py` for nicely-formatted, sectioned terminal output.

**Tech Stack:** Python 3.10+, FastAPI, Pydantic v2, Supabase (PostgREST), pytest with `asyncio_mode = "auto"`, stdlib `logging` (no new dependencies).

**Spec:** [docs/superpowers/specs/2026-04-26-backend-orchestration-rewrite-design.md](../specs/2026-04-26-backend-orchestration-rewrite-design.md)

**Branch:** `backend-rewrite` off current `backend`.

---

## Task 0: Branch setup and clean baseline

**Files:**
- No file changes — branch and verify.

- [ ] **Step 1: Create the rewrite branch**

Run:
```bash
git checkout -b backend-rewrite
git status
```
Expected: clean tree on `backend-rewrite`.

- [ ] **Step 2: Verify pytest baseline still passes against current code**

Run:
```bash
pytest -q
```
Expected: all tests pass (or at least: pre-existing failures are documented and unrelated to this rewrite). Note any failing tests in `git status` output of the next commit message.

- [ ] **Step 3: Commit baseline marker (no code change, just message)**

```bash
git commit --allow-empty -m "chore: start backend-rewrite branch"
```

---

## Task 1: Add `Recommendation` reshape (failing test first)

**Files:**
- Test: `tests/test_recommendation_shape.py`
- Modify: `shared/models.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_recommendation_shape.py`:

```python
"""Recommendation surface fields after EV reconciliation.

The math owner moved confidence from a categorical string to a numeric
``confidence_percentage``, added ``expected_profit_grailed`` (q50 net of
Grailed fees minus buy_cost), and added ``buy_cost`` (listing + NYC tax +
shipping). The Recommendation surface promotes these instead of the legacy
``edge_usd``/``cost``/``confidence`` triple.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from shared.models import (
    LiveListing,
    LivePrice,
    Recommendation,
    Seller,
    SellerBadges,
)


def _live() -> LiveListing:
    return LiveListing(
        id="abc",
        url="https://www.grailed.com/listings/abc",
        designer="Maison Margiela",
        name="Replica GAT",
        size="42",
        condition_raw="Gently Used",
        location="US",
        color="White",
        image_urls=[],
        price=LivePrice(listing_price_usd=189, shipping_price_usd=15),
        seller=Seller(
            seller_name="tester",
            reviews_count=0,
            transactions_count=0,
            items_for_sale_count=0,
            posted_at_unix=1700000000,
            badges=SellerBadges(verified=False, trusted_seller=False, quick_responder=False, speedy_shipper=False),
        ),
        description="",
    )


def test_recommendation_carries_new_top_level_fields():
    rec = Recommendation(
        item_id="abc",
        scraped_at_unix=1700000000,
        query="margiela gats",
        expected_profit_grailed=122.0,
        expected_profit_off_grailed=153.0,
        buy_cost=189.0,
        p_sell=0.71,
        q50=342.0,
        confidence_pct=78.0,
        valuation={"id": "abc", "metrics": {}},
        sell_probability={"p_sell": 0.71},
        live_listing=_live(),
    )
    assert rec.expected_profit_grailed == 122.0
    assert rec.expected_profit_off_grailed == 153.0
    assert rec.buy_cost == 189.0
    assert rec.confidence_pct == 78.0
    assert rec.q50 == 342.0


def test_recommendation_rejects_legacy_fields():
    """Legacy fields must not accept silently — they are removed from the surface.

    Pydantic by default ignores unknown fields, so we explicitly assert they
    are not present as attributes after construction.
    """
    rec = Recommendation(
        item_id="abc",
        scraped_at_unix=1700000000,
        query="margiela gats",
        expected_profit_grailed=10.0,
        expected_profit_off_grailed=12.0,
        buy_cost=100.0,
        p_sell=0.5,
        q50=110.0,
        confidence_pct=50.0,
        valuation={},
        sell_probability={},
        live_listing=_live(),
    )
    assert not hasattr(rec, "edge_usd")
    assert not hasattr(rec, "cost")
    assert not hasattr(rec, "confidence")


def test_recommendation_required_fields_missing_raises():
    with pytest.raises(ValidationError):
        Recommendation(
            item_id="abc",
            scraped_at_unix=1700000000,
            query="x",
            # Missing expected_profit_grailed
            expected_profit_off_grailed=1.0,
            buy_cost=1.0,
            p_sell=0.1,
            q50=1.0,
            confidence_pct=1.0,
            valuation={},
            sell_probability={},
            live_listing=_live(),
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_recommendation_shape.py -v
```
Expected: FAIL — current `Recommendation` has `edge_usd`/`cost`/`confidence` and rejects the new field names.

- [ ] **Step 3: Replace the `Recommendation` class in `shared/models.py`**

Open `shared/models.py`. Replace the existing `Recommendation` class (the one starting `class Recommendation(BaseModel):`) with:

```python
class Recommendation(BaseModel):
    """One ranked recommendation. Single shape returned by both ``/search``
    and ``/recommendations`` so the frontend writes one renderer.

    Top-level fields are extracted from EV outputs at construction time so
    callers can sort/filter without digging into JSONB. ``valuation`` and
    ``sell_probability`` stay as ``dict`` so the math owner can add fields
    additively without API churn.

    Sold comparables are intentionally NOT included — the valuation already
    summarizes them and raw comps aren't useful for display.
    """

    item_id: str
    scraped_at_unix: int
    query: str

    # Ranking + cost surface (sourced from EV's new fields — see
    # ev/EV_MODEL_SPEC.md §3.4)
    expected_profit_grailed: float
    expected_profit_off_grailed: float
    buy_cost: float
    p_sell: float
    q50: float
    confidence_pct: float

    # Opaque payloads — schemas owned by ev/EV_MODEL_SPEC.md
    valuation: dict
    sell_probability: dict
    live_listing: LiveListing
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_recommendation_shape.py -v
```
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add tests/test_recommendation_shape.py shared/models.py
git commit -m "feat(models): reshape Recommendation around EV's new output fields"
```

---

## Task 2: Delete agent and hype models from `shared/models.py`

**Files:**
- Modify: `shared/models.py`

- [ ] **Step 1: Confirm callers of the to-be-deleted models**

Run:
```bash
grep -rn "AgentRunRequest\|CandidateQuery\|PlanPickedQuery\|PlanSkippedQuery\|AgentPlan\|SummaryHighlight\|AgentSummary\|HypeProbeResult\|AgentRunState\|HypeResult\|TrendSeries\|TrendPoint\|RelatedQuery\|HypeEvidence" --include="*.py" backend/ shared/ tests/ 2>/dev/null
```
Expected: hits in `backend/orchestrator.py`, `backend/main.py`, `backend/agent/*.py`, `tests/test_orchestrator.py`, `tests/test_agent_llm.py`. All are scheduled for deletion in later tasks. The only remaining import of `HypeResult` etc. after this rewrite will be inside the to-be-deleted modules.

- [ ] **Step 2: Delete the model classes from `shared/models.py`**

Open `shared/models.py`. Delete these classes entirely (in source order):

- `TrendPoint`
- `TrendSeries`
- `RelatedQuery`
- `HypeEvidence`
- `HypeResult`
- `AgentRunRequest`
- `CandidateQuery`
- `PlanPickedQuery`
- `PlanSkippedQuery`
- `AgentPlan`
- `SummaryHighlight`
- `AgentSummary`
- `HypeProbeResult`
- `AgentRunState`

Keep: `SearchParams`, `EVDistribution`, `SellerBadges`, `Seller`, `LivePrice`, `SoldPrice`, `LiveListing`, `SoldListing`, `GrailedResultRow`, `ScrapeMetadata`, `GrailedScrapeResult`, `Recommendation`, `SearchResponse`.

After the edit, `from typing import Literal` may have no remaining users — leave the import; if `ruff`/`pyflakes` runs in CI, remove it.

- [ ] **Step 3: Verify the file still parses**

Run:
```bash
python -c "from shared.models import SearchParams, Recommendation, SearchResponse, GrailedScrapeResult; print('ok')"
```
Expected: `ok`. If `ImportError` for `LiveListing`/`SoldListing` etc., you accidentally deleted a kept class — restore.

- [ ] **Step 4: Confirm deleted classes are gone**

Run:
```bash
python -c "from shared.models import HypeResult" 2>&1 | grep -i "ImportError\|cannot import"
```
Expected: an `ImportError`/`cannot import name` message (proves deletion).

- [ ] **Step 5: Commit**

```bash
git add shared/models.py
git commit -m "refactor(models): delete agent and hype models (endpoints being removed)"
```

---

## Task 3: Delete `backend/agent/` and `tests/test_agent_llm.py`

**Files:**
- Delete: `backend/agent/` (entire directory)
- Delete: `tests/test_agent_llm.py`

- [ ] **Step 1: Remove the agent package**

Run:
```bash
git rm -r backend/agent/
git rm tests/test_agent_llm.py
```
Expected: 6 files removed (`__init__.py`, `intent.py`, `llm.py`, `planner.py`, `summary.py`, `tests/test_agent_llm.py`).

- [ ] **Step 2: Verify nothing imports from `backend.agent`**

Run:
```bash
grep -rn "from backend.agent\|import backend.agent" --include="*.py" .
```
Expected: hits only in `backend/orchestrator.py` (cleaned up in Task 4) and possibly the old `tests/test_orchestrator.py` (deleted in Task 8).

- [ ] **Step 3: Commit**

```bash
git commit -m "refactor: delete backend/agent — flow being removed pending rebuild"
```

---

## Task 4: Strip `backend/orchestrator.py` to nothing (will be replaced by `pipeline/search.py`)

**Files:**
- Delete: `backend/orchestrator.py`

- [ ] **Step 1: Delete the orchestrator**

Run:
```bash
git rm backend/orchestrator.py
```

- [ ] **Step 2: Verify the package still loads (importing `backend` should not fail)**

Run:
```bash
python -c "import backend" 2>&1 | head -5
```
Expected: succeeds silently. (The package has no `__init__.py` content that imports orchestrator.)

- [ ] **Step 3: Confirm `backend/main.py` will fail to import (we expect this — fixed in Task 11)**

Run:
```bash
python -c "import backend.main" 2>&1 | head -5
```
Expected: `ImportError` or `ModuleNotFoundError` mentioning `orchestrator`. This is a known intermediate state; Task 11 rewrites `main.py`.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor: delete backend/orchestrator.py (replaced by pipeline/search.py in next tasks)"
```

---

## Task 5: Add `RunContext` dataclass with tests

**Files:**
- Create: `backend/pipeline/__init__.py`
- Create: `backend/pipeline/context.py`
- Test: `tests/test_run_context.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_run_context.py`:

```python
"""RunContext flows through every pipeline stage. It carries the run id,
a pre-bound logger (so log lines auto-include run_id), and accumulating
counters/timings/warnings that the presenter and structured logs both read.
"""

from __future__ import annotations

import logging

import pytest

from backend.pipeline.context import RunContext


def test_run_context_generates_unique_run_ids():
    a = RunContext()
    b = RunContext()
    assert a.run_id != b.run_id
    assert len(a.run_id) == 12  # short hex


def test_record_stage_stores_timing_and_namespaced_counts():
    ctx = RunContext()
    ctx.record_stage("scrape", duration_ms=1234, live_returned=38, total_live_found=200)
    assert ctx.timings_ms["scrape"] == 1234
    assert ctx.counts["scrape.live_returned"] == 38
    assert ctx.counts["scrape.total_live_found"] == 200


def test_add_warning_appends():
    ctx = RunContext()
    ctx.add_warning("no_data: abc")
    ctx.add_warning("no_data: def")
    assert ctx.warnings == ["no_data: abc", "no_data: def"]


def test_total_ms_is_monotonic_and_nonnegative():
    ctx = RunContext()
    assert ctx.total_ms >= 0


def test_logger_emits_run_id_in_extra(caplog):
    ctx = RunContext()
    with caplog.at_level(logging.INFO, logger="backend"):
        ctx.logger.info("hello", extra={"stage": "test"})

    assert any(
        getattr(record, "run_id", None) == ctx.run_id and record.message == "hello"
        for record in caplog.records
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_run_context.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.pipeline'`.

- [ ] **Step 3: Create the package**

Create `backend/pipeline/__init__.py` (empty file):

```python
```

Create `backend/pipeline/context.py`:

```python
"""Per-run state passed through every pipeline stage.

Holds the run id, a pre-bound logger adapter (so log lines auto-include
``run_id``), and accumulating counters/timings/warnings that the presenter
and structured logs both read from. Stages mutate the context via
``record_stage`` and ``add_warning`` — no other state lives outside.
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
    logger: logging.LoggerAdapter = field(init=False)

    def __post_init__(self) -> None:
        self.logger = logging.LoggerAdapter(
            logging.getLogger("backend"),
            {"run_id": self.run_id},
        )

    def record_stage(self, stage: str, *, duration_ms: int, **counts: int) -> None:
        self.timings_ms[stage] = duration_ms
        for key, value in counts.items():
            self.counts[f"{stage}.{key}"] = value

    def add_warning(self, msg: str) -> None:
        self.warnings.append(msg)

    @property
    def total_ms(self) -> int:
        return int((monotonic() - self.started_at) * 1000)
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_run_context.py -v
```
Expected: PASS (5 passed).

Note: `caplog` captures records from the underlying `logging.Logger`, not the adapter. The `LoggerAdapter` injects `extra` into the log record's `__dict__`, so `record.run_id` is accessible.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/__init__.py backend/pipeline/context.py tests/test_run_context.py
git commit -m "feat(pipeline): add RunContext for per-run state and bound logger"
```

---

## Task 6: Add structured logging setup with tests

**Files:**
- Create: `backend/logging_setup.py`
- Test: `tests/test_logging_setup.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_logging_setup.py`:

```python
"""Logging configuration: JSON formatter by default, key=value via
LOG_FORMAT=text. Both formatters merge any ``extra`` fields onto the line.
"""

from __future__ import annotations

import io
import json
import logging

import pytest

from backend.logging_setup import (
    JsonFormatter,
    KeyValueFormatter,
    configure_logging,
)


def _emit_with_formatter(formatter: logging.Formatter, *, extra: dict) -> str:
    logger = logging.getLogger("test.logging_setup")
    logger.handlers.clear()
    logger.propagate = False
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("hello", extra=extra)
    return buf.getvalue().strip()


def test_json_formatter_emits_required_fields():
    line = _emit_with_formatter(JsonFormatter(), extra={"run_id": "abc", "stage": "scrape"})
    payload = json.loads(line)
    assert payload["msg"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logging_setup"
    assert payload["run_id"] == "abc"
    assert payload["stage"] == "scrape"
    assert "ts" in payload


def test_key_value_formatter_includes_extras_and_msg():
    line = _emit_with_formatter(KeyValueFormatter(), extra={"run_id": "abc", "duration_ms": 42})
    assert "run_id=abc" in line
    assert "duration_ms=42" in line
    assert "INFO" in line
    assert "hello" in line


def test_configure_logging_defaults_to_json(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging(level="INFO")
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, JsonFormatter)


def test_configure_logging_text_override(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    configure_logging(level="INFO")
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, KeyValueFormatter)


def test_configure_logging_clears_existing_handlers(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    root.addHandler(logging.NullHandler())
    configure_logging(level="DEBUG")
    assert len(root.handlers) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run:
```bash
pytest tests/test_logging_setup.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'backend.logging_setup'`.

- [ ] **Step 3: Create `backend/logging_setup.py`**

```python
"""Configure root logger. Call once from ``main.py:lifespan`` and ``cli.py:main``.

Default: JSON-line formatter (one object per line). Set ``LOG_FORMAT=text``
for key=value formatting in casual terminal tails.
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
        payload: dict[str, object] = {
            "ts": datetime.now(tz=UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
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
        line = f"{base} {extras} msg={msg!r}".strip().replace("  ", " ")
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging(level: str = "INFO") -> None:
    fmt = os.environ.get("LOG_FORMAT", "json").lower()
    formatter: logging.Formatter
    formatter = JsonFormatter() if fmt == "json" else KeyValueFormatter()
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
```

- [ ] **Step 4: Run test to verify it passes**

Run:
```bash
pytest tests/test_logging_setup.py -v
```
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/logging_setup.py tests/test_logging_setup.py
git commit -m "feat(logging): add structured logging (JSON default, text override via env)"
```

---

## Task 7: Add the search pipeline (`backend/pipeline/search.py`) with stage tests

This is the largest task. Split into three commits: stages-pure-logic, persist-stage, then `run_search` end-to-end.

**Files:**
- Create: `backend/pipeline/search.py`
- Test: `tests/test_pipeline_search.py`

### 7a — `_value_stage` and `_rank_stage` (pure functions, no I/O)

- [ ] **Step 1: Write failing tests for value + rank stages**

Create `tests/test_pipeline_search.py`:

```python
"""Pipeline stage tests. Stages are private (`_value_stage`, `_rank_stage`,
`_scrape_stage`, `_persist_stage`); the public surface is `run_search`."""

from __future__ import annotations

import asyncio

import pytest

from backend.pipeline import search as pipeline_search
from backend.pipeline.context import RunContext
from shared.models import (
    GrailedResultRow,
    GrailedScrapeResult,
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchParams,
    SearchResponse,
    Seller,
    SellerBadges,
    SoldListing,
    SoldPrice,
)


def _seller() -> Seller:
    return Seller(
        seller_name="tester",
        reviews_count=10,
        transactions_count=20,
        items_for_sale_count=3,
        posted_at_unix=1700000000,
        badges=SellerBadges(verified=True, trusted_seller=False, quick_responder=False, speedy_shipper=False),
    )


def _live(listing_id: str) -> LiveListing:
    return LiveListing(
        id=listing_id,
        url=f"https://www.grailed.com/listings/{listing_id}",
        designer="Guidi",
        name=f"Boot {listing_id}",
        size="43",
        condition_raw="Gently Used",
        location="US",
        color="Black",
        image_urls=[],
        price=LivePrice(listing_price_usd=700, shipping_price_usd=25),
        seller=_seller(),
        description="desc",
    )


def _sold(listing_id: str) -> SoldListing:
    return SoldListing(
        id=f"sold-{listing_id}",
        url=f"https://www.grailed.com/listings/sold-{listing_id}",
        designer="Guidi",
        name=f"Sold Boot {listing_id}",
        size="43",
        condition_raw="Used",
        location="US",
        color="Black",
        image_urls=[],
        price=SoldPrice(sold_price_usd=650, shipping_price_usd=20),
        sold_at_unix=1700000500,
        seller=_seller(),
        description="desc",
    )


def _row(listing_id: str, *, sold_count: int = 1) -> GrailedResultRow:
    return GrailedResultRow(
        live_listing=_live(listing_id),
        sold_comparables=[_sold(f"{listing_id}-{i}") for i in range(sold_count)],
    )


def _scrape_result(row_specs: list[tuple[str, int]]) -> GrailedScrapeResult:
    return GrailedScrapeResult(
        metadata=ScrapeMetadata(
            query="guidi",
            categories=["menswear"],
            live_limit_requested=10,
            sold_limit_requested=10,
            scraped_at_unix=1700000000,
            total_live_found=len(row_specs),
        ),
        results=[_row(rid, sold_count=sc) for rid, sc in row_specs],
    )


def _valuation_success(*, expected_profit_grailed: float, q50: float = 800.0) -> dict:
    return {
        "id": "x",
        "name": "x",
        "cost": 725.0,
        "buy_cost": 786.21,
        "dist": {"q10": 600.0, "q50": q50, "q90": 900.0},
        "metrics": {
            "edge_usd": q50 - 725.0,
            "expected_profit_grailed": expected_profit_grailed,
            "expected_profit_off_grailed": expected_profit_grailed + 30.0,
            "expected_profit_grailed_pct": expected_profit_grailed / 786.21,
            "expected_profit_off_grailed_pct": (expected_profit_grailed + 30.0) / 786.21,
            "grailed_total_fees": 100.0,
            "grailed_net_payout": q50 - 100.0,
            "effective_n": 4.0,
            "confidence_percentage": 72.5,
            "num_valid_price_comps": 5,
            "num_valid_time_comps": 3,
        },
    }


def _sell_prob() -> dict:
    return {
        "p_sell": 0.55,
        "horizon_days": 7,
        "median_days_to_sell": 18.0,
        "adjusted_days_to_sell": 17.2,
        "pricing_ratio": 1.0,
        "live_price": 725.0,
        "q50_comp_price": 700.0,
        "num_valid_time_comps": 2,
        "num_sold_comps": 3,
    }


# -------- _value_stage --------

def test_value_stage_drops_no_data_rows_and_records_count(monkeypatch):
    scrape = _scrape_result([("a", 2), ("b", 2)])
    ctx = RunContext()

    def _value_listing(row_dict, scraped_at):
        if row_dict["live_listing"]["id"] == "a":
            return {"id": "a", "status": "no_data"}
        return _valuation_success(expected_profit_grailed=120.0)

    monkeypatch.setattr(pipeline_search, "value_listing", _value_listing)
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())

    items = pipeline_search._value_stage(scrape, SearchParams(query="guidi"), ctx)

    assert [i.item_id for i in items] == ["b"]
    assert ctx.counts["value.no_data"] == 1
    assert ctx.counts["value.valued"] == 1
    assert ctx.counts["value.errored"] == 0
    assert ctx.counts["value.sold_comps_total"] == 4  # 2 + 2
    assert any("no_data: a" in w for w in ctx.warnings)


def test_value_stage_extracts_new_top_level_fields(monkeypatch):
    scrape = _scrape_result([("only", 1)])
    ctx = RunContext()
    monkeypatch.setattr(
        pipeline_search,
        "value_listing",
        lambda row, scraped_at: _valuation_success(expected_profit_grailed=88.0, q50=900.0),
    )
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())

    items = pipeline_search._value_stage(scrape, SearchParams(query="guidi"), ctx)

    assert len(items) == 1
    rec = items[0]
    assert rec.expected_profit_grailed == 88.0
    assert rec.expected_profit_off_grailed == 118.0
    assert rec.buy_cost == 786.21
    assert rec.confidence_pct == 72.5
    assert rec.q50 == 900.0


def test_value_stage_per_row_exception_drops_row_and_counts_errored(monkeypatch):
    scrape = _scrape_result([("a", 1), ("b", 1)])
    ctx = RunContext()

    def _value_listing(row_dict, scraped_at):
        if row_dict["live_listing"]["id"] == "a":
            raise RuntimeError("bad row")
        return _valuation_success(expected_profit_grailed=10.0)

    monkeypatch.setattr(pipeline_search, "value_listing", _value_listing)
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())

    items = pipeline_search._value_stage(scrape, SearchParams(query="guidi"), ctx)

    assert [i.item_id for i in items] == ["b"]
    assert ctx.counts["value.errored"] == 1
    assert ctx.counts["value.valued"] == 1


# -------- _rank_stage --------

def test_rank_stage_orders_by_p_sell_times_expected_profit_grailed():
    ctx = RunContext()
    items = [
        Recommendation(
            item_id="lo", scraped_at_unix=0, query="q",
            expected_profit_grailed=10.0, expected_profit_off_grailed=12.0,
            buy_cost=100.0, p_sell=0.5, q50=110.0, confidence_pct=50.0,
            valuation={}, sell_probability={}, live_listing=_live("lo"),
        ),
        Recommendation(
            item_id="hi", scraped_at_unix=0, query="q",
            expected_profit_grailed=200.0, expected_profit_off_grailed=220.0,
            buy_cost=300.0, p_sell=0.5, q50=500.0, confidence_pct=70.0,
            valuation={}, sell_probability={}, live_listing=_live("hi"),
        ),
        Recommendation(
            item_id="mid", scraped_at_unix=0, query="q",
            expected_profit_grailed=80.0, expected_profit_off_grailed=90.0,
            buy_cost=200.0, p_sell=0.9, q50=280.0, confidence_pct=60.0,
            valuation={}, sell_probability={}, live_listing=_live("mid"),
        ),
    ]
    # scores: lo=5, hi=100, mid=72  -> hi, mid, lo
    ranked = pipeline_search._rank_stage(items, ctx)
    assert [i.item_id for i in ranked] == ["hi", "mid", "lo"]
    assert ctx.counts["rank.ranked"] == 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/test_pipeline_search.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.pipeline.search'` (or `AttributeError` once partial files exist).

- [ ] **Step 3: Create `backend/pipeline/search.py` with `_value_stage` and `_rank_stage`**

```python
"""Search pipeline. Public surface: ``run_search``.

Stages are private functions in this file. Each stage:
  1. Logs ``stage_started`` on entry.
  2. Records start time.
  3. Runs its work.
  4. Records timing + counts on the ``RunContext``.
  5. Logs ``stage_completed`` with merged extras.

Errors propagate from the scrape stage. Per-row EV exceptions are caught,
counted, and warned. Persistence failures are caught and warned.
"""

from __future__ import annotations

from time import monotonic

from ev import estimate_sell_probability, value_listing
from scraper.scraper import scrape
from shared.models import (
    GrailedScrapeResult,
    Recommendation,
    SearchParams,
    SearchResponse,
)
from shared.store import get_recommendations_store

from backend.pipeline.context import RunContext


def _value_stage(
    scrape_result: GrailedScrapeResult,
    params: SearchParams,
    ctx: RunContext,
) -> list[Recommendation]:
    ctx.logger.info("stage_started", extra={"stage": "value"})
    started = monotonic()

    items: list[Recommendation] = []
    no_data = 0
    errored = 0
    sold_comps_total = 0
    sold_comps_with_data = 0
    scraped_at = scrape_result.metadata.scraped_at_unix

    for row in scrape_result.results:
        sold_comps_total += len(row.sold_comparables)
        try:
            row_dict = row.model_dump(mode="json")
            valuation = value_listing(row_dict, scraped_at)
        except Exception as exc:
            errored += 1
            ctx.logger.warning(
                "value_row_errored",
                extra={"stage": "value", "item_id": row.live_listing.id, "error": str(exc)},
            )
            ctx.add_warning(
                f"errored: {row.live_listing.id} ({row.live_listing.designer} {row.live_listing.name})"
            )
            continue

        if valuation.get("status") == "no_data":
            no_data += 1
            ctx.add_warning(
                f"no_data: {row.live_listing.id} ({row.live_listing.designer} {row.live_listing.name})"
            )
            continue

        try:
            sell_prob = estimate_sell_probability(row_dict)
        except Exception as exc:
            errored += 1
            ctx.logger.warning(
                "sell_prob_row_errored",
                extra={"stage": "value", "item_id": row.live_listing.id, "error": str(exc)},
            )
            continue

        metrics = valuation.get("metrics", {})
        try:
            rec = Recommendation(
                item_id=row.live_listing.id,
                scraped_at_unix=scraped_at,
                query=params.query,
                expected_profit_grailed=float(metrics["expected_profit_grailed"]),
                expected_profit_off_grailed=float(metrics["expected_profit_off_grailed"]),
                buy_cost=float(valuation["buy_cost"]),
                p_sell=float(sell_prob["p_sell"]),
                q50=float(valuation["dist"]["q50"]),
                confidence_pct=float(metrics["confidence_percentage"]),
                valuation=valuation,
                sell_probability=sell_prob,
                live_listing=row.live_listing,
            )
        except (KeyError, ValueError, TypeError) as exc:
            errored += 1
            ctx.logger.warning(
                "value_row_shape_mismatch",
                extra={"stage": "value", "item_id": row.live_listing.id, "error": str(exc)},
            )
            continue

        items.append(rec)
        sold_comps_with_data += len(row.sold_comparables)

    duration_ms = int((monotonic() - started) * 1000)
    ctx.record_stage(
        "value",
        duration_ms=duration_ms,
        valued=len(items),
        no_data=no_data,
        errored=errored,
        sold_comps_total=sold_comps_total,
        sold_comps_with_data=sold_comps_with_data,
    )
    ctx.logger.info(
        "stage_completed",
        extra={
            "stage": "value",
            "duration_ms": duration_ms,
            "valued": len(items),
            "no_data": no_data,
            "errored": errored,
        },
    )
    return items


def _rank_stage(items: list[Recommendation], ctx: RunContext) -> list[Recommendation]:
    ctx.logger.info("stage_started", extra={"stage": "rank"})
    started = monotonic()
    ranked = sorted(items, key=lambda r: r.p_sell * r.expected_profit_grailed, reverse=True)
    duration_ms = int((monotonic() - started) * 1000)
    ctx.record_stage("rank", duration_ms=duration_ms, ranked=len(ranked))
    ctx.logger.info(
        "stage_completed",
        extra={"stage": "rank", "duration_ms": duration_ms, "ranked": len(ranked)},
    )
    return ranked
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```bash
pytest tests/test_pipeline_search.py -v
```
Expected: PASS for `_value_stage` and `_rank_stage` tests (5 passed). Other tests in the file (added later) may not exist yet.

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/search.py tests/test_pipeline_search.py
git commit -m "feat(pipeline): add value and rank stages"
```

### 7b — `_scrape_stage` and `_persist_stage`

- [ ] **Step 1: Append failing tests for scrape + persist stages**

Append to `tests/test_pipeline_search.py`:

```python
# -------- _scrape_stage --------

def test_scrape_stage_calls_scraper_and_records_counts(monkeypatch):
    captured: list[bool] = []

    async def _scrape_stub(params, *, persist):
        captured.append(persist)
        return _scrape_result([("a", 3), ("b", 2)])

    monkeypatch.setattr(pipeline_search, "scrape", _scrape_stub)

    ctx = RunContext()
    result = asyncio.run(
        pipeline_search._scrape_stage(SearchParams(query="guidi", live_limit=10), ctx, persist=False)
    )

    assert captured == [False]
    assert len(result.results) == 2
    assert ctx.timings_ms.get("scrape") is not None
    assert ctx.counts["scrape.live_returned"] == 2
    assert ctx.counts["scrape.live_requested"] == 10
    assert ctx.counts["scrape.total_live_found"] == 2


# -------- _persist_stage --------

class _FakeStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def save_recommendations(self, *, response, params) -> None:
        self.calls.append({"response": response, "params": params})


def test_persist_stage_writes_when_store_set(monkeypatch):
    fake = _FakeStore()
    monkeypatch.setattr(pipeline_search, "get_recommendations_store", lambda: fake)
    ctx = RunContext()
    response = SearchResponse(
        metadata=_scrape_result([]).metadata,
        items=[
            Recommendation(
                item_id="a", scraped_at_unix=0, query="q",
                expected_profit_grailed=10.0, expected_profit_off_grailed=12.0,
                buy_cost=100.0, p_sell=0.5, q50=110.0, confidence_pct=50.0,
                valuation={}, sell_probability={}, live_listing=_live("a"),
            ),
        ],
    )
    pipeline_search._persist_stage(response, SearchParams(query="q"), ctx)

    assert len(fake.calls) == 1
    assert ctx.counts["persist.inserted"] == 1


def test_persist_stage_no_store_warns_and_counts_zero(monkeypatch, caplog):
    monkeypatch.setattr(pipeline_search, "get_recommendations_store", lambda: None)
    ctx = RunContext()
    response = SearchResponse(metadata=_scrape_result([]).metadata, items=[])
    pipeline_search._persist_stage(response, SearchParams(query="q"), ctx)

    assert ctx.counts["persist.inserted"] == 0
    assert any("no recommendations store" in w.lower() for w in ctx.warnings)


def test_persist_stage_swallows_store_exception_and_warns(monkeypatch):
    class _BadStore:
        def save_recommendations(self, *, response, params):
            raise RuntimeError("DB down")

    monkeypatch.setattr(pipeline_search, "get_recommendations_store", lambda: _BadStore())
    ctx = RunContext()
    response = SearchResponse(
        metadata=_scrape_result([]).metadata,
        items=[
            Recommendation(
                item_id="a", scraped_at_unix=0, query="q",
                expected_profit_grailed=1.0, expected_profit_off_grailed=1.0,
                buy_cost=1.0, p_sell=0.5, q50=2.0, confidence_pct=10.0,
                valuation={}, sell_probability={}, live_listing=_live("a"),
            )
        ],
    )

    pipeline_search._persist_stage(response, SearchParams(query="q"), ctx)

    assert ctx.counts["persist.inserted"] == 0
    assert any("persist failed" in w.lower() for w in ctx.warnings)
```

- [ ] **Step 2: Run new tests to verify they fail**

Run:
```bash
pytest tests/test_pipeline_search.py -v -k "scrape_stage or persist_stage"
```
Expected: FAIL with `AttributeError: module 'backend.pipeline.search' has no attribute '_scrape_stage'`.

- [ ] **Step 3: Append `_scrape_stage` and `_persist_stage` to `backend/pipeline/search.py`**

Append below the existing functions:

```python
async def _scrape_stage(
    params: SearchParams,
    ctx: RunContext,
    *,
    persist: bool,
) -> GrailedScrapeResult:
    ctx.logger.info("stage_started", extra={"stage": "scrape", "query": params.query})
    started = monotonic()
    result = await scrape(params, persist=persist)
    duration_ms = int((monotonic() - started) * 1000)
    ctx.record_stage(
        "scrape",
        duration_ms=duration_ms,
        live_requested=params.live_limit,
        live_returned=len(result.results),
        total_live_found=result.metadata.total_live_found,
    )
    ctx.logger.info(
        "stage_completed",
        extra={
            "stage": "scrape",
            "duration_ms": duration_ms,
            "live_returned": len(result.results),
            "total_live_found": result.metadata.total_live_found,
        },
    )
    return result


def _persist_stage(
    response: SearchResponse,
    params: SearchParams,
    ctx: RunContext,
) -> None:
    ctx.logger.info("stage_started", extra={"stage": "persist"})
    started = monotonic()
    store = get_recommendations_store()
    inserted = 0
    if store is None:
        ctx.add_warning("persist skipped: no recommendations store wired")
        ctx.logger.warning("persist_skipped", extra={"stage": "persist"})
    else:
        try:
            store.save_recommendations(response=response, params=params)
            inserted = len(response.items)
        except Exception as exc:
            ctx.add_warning(f"persist failed: {exc}")
            ctx.logger.error(
                "persist_failed",
                extra={"stage": "persist", "error": str(exc)},
                exc_info=True,
            )
    duration_ms = int((monotonic() - started) * 1000)
    ctx.record_stage("persist", duration_ms=duration_ms, inserted=inserted)
    ctx.logger.info(
        "stage_completed",
        extra={"stage": "persist", "duration_ms": duration_ms, "inserted": inserted},
    )
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```bash
pytest tests/test_pipeline_search.py -v
```
Expected: PASS (all 9 tests so far).

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/search.py tests/test_pipeline_search.py
git commit -m "feat(pipeline): add scrape and persist stages"
```

### 7c — `run_search` orchestrator

- [ ] **Step 1: Append failing tests for `run_search`**

Append to `tests/test_pipeline_search.py`:

```python
# -------- run_search --------

def test_run_search_end_to_end_with_persist(monkeypatch):
    scrape = _scrape_result([("a", 1), ("b", 1)])

    async def _scrape_stub(params, *, persist):
        return scrape

    fake = _FakeStore()
    monkeypatch.setattr(pipeline_search, "scrape", _scrape_stub)
    monkeypatch.setattr(pipeline_search, "value_listing", lambda r, s: _valuation_success(expected_profit_grailed=50.0))
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())
    monkeypatch.setattr(pipeline_search, "get_recommendations_store", lambda: fake)

    ctx = RunContext()
    response = asyncio.run(
        pipeline_search.run_search(SearchParams(query="guidi", live_limit=2), ctx, persist=True)
    )

    assert len(response.items) == 2
    assert ctx.timings_ms.keys() >= {"scrape", "value", "rank", "persist"}
    assert ctx.counts["persist.inserted"] == 2


def test_run_search_persist_false_skips_persist_stage(monkeypatch):
    scrape = _scrape_result([("a", 1)])

    async def _scrape_stub(params, *, persist):
        return scrape

    fake = _FakeStore()
    monkeypatch.setattr(pipeline_search, "scrape", _scrape_stub)
    monkeypatch.setattr(pipeline_search, "value_listing", lambda r, s: _valuation_success(expected_profit_grailed=10.0))
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())
    monkeypatch.setattr(pipeline_search, "get_recommendations_store", lambda: fake)

    ctx = RunContext()
    asyncio.run(pipeline_search.run_search(SearchParams(query="guidi"), ctx, persist=False))

    assert "persist" not in ctx.timings_ms
    assert fake.calls == []


def test_run_search_returns_empty_items_when_all_no_data(monkeypatch):
    scrape = _scrape_result([("a", 1), ("b", 1)])

    async def _scrape_stub(params, *, persist):
        return scrape

    monkeypatch.setattr(pipeline_search, "scrape", _scrape_stub)
    monkeypatch.setattr(pipeline_search, "value_listing", lambda r, s: {"status": "no_data"})
    monkeypatch.setattr(pipeline_search, "estimate_sell_probability", lambda r: _sell_prob())
    monkeypatch.setattr(pipeline_search, "get_recommendations_store", lambda: None)

    ctx = RunContext()
    response = asyncio.run(pipeline_search.run_search(SearchParams(query="guidi"), ctx))

    assert response.items == []
    assert ctx.counts["value.no_data"] == 2
    assert response.metadata.scraped_at_unix == scrape.metadata.scraped_at_unix
```

- [ ] **Step 2: Run new tests to verify they fail**

Run:
```bash
pytest tests/test_pipeline_search.py -v -k "run_search"
```
Expected: FAIL — `run_search` not defined.

- [ ] **Step 3: Append `run_search` to `backend/pipeline/search.py`**

```python
async def run_search(
    params: SearchParams,
    ctx: RunContext,
    *,
    persist: bool = True,
) -> SearchResponse:
    """Scrape -> value -> rank -> (optional) persist. Returns ranked SearchResponse.

    Errors from scraper propagate. Per-row EV failures are dropped+counted.
    Persistence failures are swallowed (warned), not raised — the caller
    already paid the scrape cost and gets the response either way.
    """
    ctx.logger.info(
        "run_started",
        extra={
            "query": params.query,
            "live_limit": params.live_limit,
            "sold_limit": params.sold_limit,
            "persist": persist,
        },
    )
    scrape_result = await _scrape_stage(params, ctx, persist=persist)
    valued = _value_stage(scrape_result, params, ctx)
    ranked = _rank_stage(valued, ctx)
    response = SearchResponse(metadata=scrape_result.metadata, items=ranked)
    if persist:
        _persist_stage(response, params, ctx)
    ctx.logger.info(
        "run_completed",
        extra={"total_ms": ctx.total_ms, **ctx.counts},
    )
    return response
```

- [ ] **Step 4: Run all pipeline tests to verify pass**

Run:
```bash
pytest tests/test_pipeline_search.py -v
```
Expected: PASS (all 12 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/pipeline/search.py tests/test_pipeline_search.py
git commit -m "feat(pipeline): add run_search end-to-end orchestration"
```

---

## Task 8: Delete the old orchestrator tests

**Files:**
- Delete: `tests/test_orchestrator.py`

- [ ] **Step 1: Confirm tests are obsolete**

The file references `backend.orchestrator` (deleted in Task 4) and old top-level fields (`edge_usd`, `cost`, `confidence`) that no longer exist on `Recommendation`. The replacement coverage lives in `tests/test_pipeline_search.py`.

- [ ] **Step 2: Remove the file**

Run:
```bash
git rm tests/test_orchestrator.py
```

- [ ] **Step 3: Verify no other test imports it**

Run:
```bash
grep -rn "test_orchestrator\|backend.orchestrator" --include="*.py" tests/ 2>/dev/null
```
Expected: no output.

- [ ] **Step 4: Commit**

```bash
git commit -m "test: remove obsolete test_orchestrator (replaced by test_pipeline_search)"
```

---

## Task 9: Update `shared/store.py:save_recommendations` for new columns

**Files:**
- Modify: `shared/store.py`
- Test: `tests/test_store_recommendations.py` (replace file)

- [ ] **Step 1: Read the current test file to learn its style**

Run:
```bash
cat tests/test_store_recommendations.py
```

- [ ] **Step 2: Replace `tests/test_store_recommendations.py` with the new failing tests**

```python
"""ListingStore.save_recommendations writes the new EV-aligned column set."""

from __future__ import annotations

from shared.models import (
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchParams,
    SearchResponse,
    Seller,
    SellerBadges,
)
from shared.store import ListingStore


def _live(listing_id: str = "abc") -> LiveListing:
    return LiveListing(
        id=listing_id,
        url=f"https://www.grailed.com/listings/{listing_id}",
        designer="Margiela",
        name="Replica GAT",
        size="42",
        condition_raw="Gently Used",
        location="US",
        color="White",
        image_urls=[],
        price=LivePrice(listing_price_usd=189, shipping_price_usd=15),
        seller=Seller(
            seller_name="x", reviews_count=0, transactions_count=0,
            items_for_sale_count=0, posted_at_unix=1700000000,
            badges=SellerBadges(verified=False, trusted_seller=False, quick_responder=False, speedy_shipper=False),
        ),
        description="",
    )


def _rec(item_id: str) -> Recommendation:
    return Recommendation(
        item_id=item_id,
        scraped_at_unix=1700000000,
        query="margiela gats",
        expected_profit_grailed=122.0,
        expected_profit_off_grailed=153.0,
        buy_cost=189.0,
        p_sell=0.71,
        q50=342.0,
        confidence_pct=78.0,
        valuation={"id": item_id, "metrics": {"expected_profit_grailed": 122.0}},
        sell_probability={"p_sell": 0.71},
        live_listing=_live(item_id),
    )


class _FakeTable:
    def __init__(self) -> None:
        self.last_rows: list[dict] | None = None

    def insert(self, rows):
        self.last_rows = rows
        return self

    def execute(self):
        return None


class _FakeClient:
    def __init__(self) -> None:
        self.tables: dict[str, _FakeTable] = {}

    def table(self, name):
        self.tables.setdefault(name, _FakeTable())
        return self.tables[name]


def test_save_recommendations_writes_new_columns():
    client = _FakeClient()
    store = ListingStore(client)
    response = SearchResponse(
        metadata=ScrapeMetadata(
            query="q", categories=[], live_limit_requested=1, sold_limit_requested=1,
            scraped_at_unix=1700000000, total_live_found=1,
        ),
        items=[_rec("abc")],
    )

    store.save_recommendations(response=response, params=SearchParams(query="margiela gats"))

    rows = client.tables["recommendations"].last_rows
    assert len(rows) == 1
    row = rows[0]
    assert row["item_id"] == "abc"
    assert row["expected_profit_grailed"] == 122.0
    assert row["expected_profit_off_grailed"] == 153.0
    assert row["buy_cost"] == 189.0
    assert row["confidence_pct"] == 78.0
    assert row["q50"] == 342.0
    assert row["p_sell"] == 0.71
    # Legacy columns absent
    assert "edge_usd" not in row
    assert "cost" not in row
    assert "confidence" not in row


def test_save_recommendations_noop_when_empty():
    client = _FakeClient()
    store = ListingStore(client)
    response = SearchResponse(
        metadata=ScrapeMetadata(
            query="q", categories=[], live_limit_requested=1, sold_limit_requested=1,
            scraped_at_unix=1700000000, total_live_found=0,
        ),
        items=[],
    )
    store.save_recommendations(response=response, params=SearchParams(query="q"))
    assert "recommendations" not in client.tables
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
pytest tests/test_store_recommendations.py -v
```
Expected: FAIL — current `save_recommendations` writes legacy `edge_usd`/`cost`/`confidence` keys.

- [ ] **Step 4: Update `save_recommendations` in `shared/store.py`**

Replace the body of `save_recommendations` (the `rows = [...]` block) with:

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

- [ ] **Step 5: Run tests to verify pass**

Run:
```bash
pytest tests/test_store_recommendations.py -v
```
Expected: PASS (2 passed).

- [ ] **Step 6: Commit**

```bash
git add shared/store.py tests/test_store_recommendations.py
git commit -m "refactor(store): write new EV-aligned columns to recommendations"
```

---

## Task 10: Add Supabase migration for new column set + RPC

**Files:**
- Create: `supabase/migrations/20260426120000_recs_use_grailed_profit.sql`

- [ ] **Step 1: Create the migration**

Note: pick a real datetime stamp greater than the latest existing migration (`20260425100000`). The file below uses `20260426120000`. Adjust if you need uniqueness.

```sql
-- Recommendations table: drop legacy edge_usd/cost/confidence columns, add
-- new columns aligned with EV's current output (expected_profit_grailed,
-- expected_profit_off_grailed, buy_cost, confidence_pct). Replace the
-- list_latest_recommendations RPC to rank by the new primary metric.

drop index if exists public.recommendations_edge_usd_idx;

alter table public.recommendations
  add column expected_profit_grailed     numeric,
  add column expected_profit_off_grailed numeric,
  add column buy_cost                    numeric,
  add column confidence_pct              numeric;

-- Best-effort backfill from the JSONB payload for any pre-existing rows.
-- Rows where these fields are absent will end up null and the NOT NULL step
-- below will fail; in that case, delete those rows first and rerun.
update public.recommendations
set expected_profit_grailed     = (valuation->'metrics'->>'expected_profit_grailed')::numeric,
    expected_profit_off_grailed = (valuation->'metrics'->>'expected_profit_off_grailed')::numeric,
    buy_cost                    = (valuation->>'buy_cost')::numeric,
    confidence_pct              = (valuation->'metrics'->>'confidence_percentage')::numeric;

alter table public.recommendations
  alter column expected_profit_grailed     set not null,
  alter column expected_profit_off_grailed set not null,
  alter column buy_cost                    set not null,
  alter column confidence_pct              set not null;

alter table public.recommendations
  drop column edge_usd,
  drop column cost,
  drop column confidence;

create index recommendations_expected_profit_grailed_idx
  on public.recommendations (expected_profit_grailed desc);

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

- [ ] **Step 2: Verify file exists and is named with a timestamp > previous migration**

Run:
```bash
ls -1 supabase/migrations/ | sort | tail -3
```
Expected: the new file is the lexicographically last entry.

- [ ] **Step 3: Apply against your dev DB**

Either:
- Paste the SQL into the Supabase SQL editor and run, OR
- `supabase db push` if you have the CLI wired.

If the `set not null` step errors, run `delete from public.recommendations where (valuation->'metrics'->>'expected_profit_grailed') is null;` and re-execute the migration.

- [ ] **Step 4: Sanity-check via SQL**

Run in the SQL editor:
```sql
select column_name, data_type
from information_schema.columns
where table_name = 'recommendations'
order by ordinal_position;
```
Expected: see `expected_profit_grailed`, `expected_profit_off_grailed`, `buy_cost`, `confidence_pct`. Do NOT see `edge_usd`, `cost`, `confidence`.

- [ ] **Step 5: Commit**

```bash
git add supabase/migrations/20260426120000_recs_use_grailed_profit.sql
git commit -m "feat(db): migrate recommendations to EV-aligned columns + RPC"
```

---

## Task 11: Rewrite `backend/main.py` (FastAPI surface)

**Files:**
- Modify: `backend/main.py`
- Test: `tests/test_api_smoke.py` (replace)

- [ ] **Step 1: Inspect the current `tests/test_api_smoke.py`**

Run:
```bash
cat tests/test_api_smoke.py
```

- [ ] **Step 2: Replace `tests/test_api_smoke.py` with the new failing tests**

```python
"""FastAPI surface after the rewrite: only /health, /search, /recommendations.
Bearer auth still required on non-health routes."""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

from backend import main as backend_main
from backend.pipeline import search as pipeline_search
from shared import store as store_mod
from shared.models import (
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchParams,
    SearchResponse,
    Seller,
    SellerBadges,
)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-token")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    yield


def _rec(item_id: str) -> Recommendation:
    return Recommendation(
        item_id=item_id, scraped_at_unix=0, query="q",
        expected_profit_grailed=10.0, expected_profit_off_grailed=12.0,
        buy_cost=100.0, p_sell=0.5, q50=120.0, confidence_pct=60.0,
        valuation={}, sell_probability={},
        live_listing=LiveListing(
            id=item_id, url="https://www.grailed.com/listings/" + item_id,
            designer="x", name="x", size="42", condition_raw="Used",
            location="US", color="black", image_urls=[],
            price=LivePrice(listing_price_usd=100, shipping_price_usd=0),
            seller=Seller(
                seller_name="s", reviews_count=0, transactions_count=0,
                items_for_sale_count=0, posted_at_unix=0,
                badges=SellerBadges(verified=False, trusted_seller=False, quick_responder=False, speedy_shipper=False),
            ),
            description="",
        ),
    )


def test_health_is_public():
    with TestClient(backend_main.app) as client:
        assert client.get("/health").status_code == 200


def test_search_requires_bearer():
    with TestClient(backend_main.app) as client:
        r = client.post("/search", json={"query": "x"})
        assert r.status_code == 401


def test_search_happy_path(monkeypatch):
    async def _run_search(params, ctx, *, persist=True):
        return SearchResponse(
            metadata=ScrapeMetadata(
                query=params.query, categories=[], live_limit_requested=1,
                sold_limit_requested=1, scraped_at_unix=0, total_live_found=1,
            ),
            items=[_rec("abc")],
        )

    monkeypatch.setattr(pipeline_search, "run_search", _run_search)
    monkeypatch.setattr(backend_main, "run_search", _run_search)

    with TestClient(backend_main.app) as client:
        r = client.post(
            "/search",
            json={"query": "x", "live_limit": 1, "sold_limit": 1},
            headers={"Authorization": "Bearer test-token"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["items"][0]["item_id"] == "abc"
        assert body["items"][0]["expected_profit_grailed"] == 10.0
        assert "edge_usd" not in body["items"][0]


def test_agent_run_endpoint_is_gone():
    with TestClient(backend_main.app) as client:
        r = client.post("/agent/run", json={"intent_text": "x"}, headers={"Authorization": "Bearer test-token"})
        assert r.status_code == 404


def test_hype_endpoint_is_gone():
    with TestClient(backend_main.app) as client:
        r = client.get("/hype/guidi", headers={"Authorization": "Bearer test-token"})
        assert r.status_code == 404


def test_recommendations_returns_empty_when_store_unset(monkeypatch):
    store_mod.set_recommendations_store(None)
    with TestClient(backend_main.app) as client:
        r = client.get("/recommendations?limit=5", headers={"Authorization": "Bearer test-token"})
        assert r.status_code == 200
        assert r.json() == {"items": []}
```

Note: `TestClient(app)` triggers `lifespan` which constructs a Supabase client. The fixture's env vars satisfy the env check; the actual Supabase client will only fail at network call time, which the tests above avoid.

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
pytest tests/test_api_smoke.py -v
```
Expected: FAIL — current `main.py` still imports the deleted orchestrator.

- [ ] **Step 4: Rewrite `backend/main.py`**

Replace the entire file:

```python
"""FastAPI app: public GET /health; all other routes require Bearer token from API_KEY env."""

from __future__ import annotations

import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import Response
from supabase import create_client

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv()

from backend.logging_setup import configure_logging
from backend.pipeline.context import RunContext
from backend.pipeline.search import run_search
from ev.ev import set_store as set_ev_store
from scraper.scraper import set_store as set_scraper_store
from shared.models import (
    Recommendation,
    SearchParams,
    SearchResponse,
)
from shared.store import (
    ListingStore,
    get_recommendations_store,
    set_recommendations_store,
)

API_KEY = os.environ.get("API_KEY", "").strip()


def _is_public_path(path: str) -> bool:
    return path == "/health" or path.rstrip("/") == "/health"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
    if not API_KEY:
        raise RuntimeError("API_KEY environment variable must be set and non-empty")
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_role:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set and non-empty"
        )
    client = create_client(supabase_url, service_role)
    store = ListingStore(client)
    app.state.store = store
    set_scraper_store(store)
    set_ev_store(store)
    set_recommendations_store(store)
    try:
        yield
    finally:
        set_recommendations_store(None)


app = FastAPI(title="code-brown backend", lifespan=lifespan)


@app.middleware("http")
async def bearer_auth_middleware(request: Request, call_next):
    if _is_public_path(request.url.path):
        return await call_next(request)
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    token = auth.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, API_KEY):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.head("/health")
def health_head():
    return Response(status_code=200)


class RecommendationsResponse(BaseModel):
    items: list[Recommendation] = Field(default_factory=list)


@app.post("/search", response_model=SearchResponse)
async def search(params: SearchParams) -> SearchResponse:
    ctx = RunContext()
    return await run_search(params, ctx)


@app.get("/recommendations", response_model=RecommendationsResponse)
def recommendations(limit: int = Query(default=50, ge=1, le=200)) -> RecommendationsResponse:
    store = get_recommendations_store()
    if store is None:
        return RecommendationsResponse(items=[])
    rows = store.list_recommendations(limit=limit)
    items = [Recommendation.model_validate(r) for r in rows]
    items.sort(key=lambda r: r.expected_profit_grailed, reverse=True)
    return RecommendationsResponse(items=items)
```

- [ ] **Step 5: Run tests to verify pass**

Run:
```bash
pytest tests/test_api_smoke.py -v
```
Expected: PASS (6 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/main.py tests/test_api_smoke.py
git commit -m "refactor(api): slim main.py to /health, /search, /recommendations; remove agent and hype"
```

---

## Task 12: Add the CLI presenter

**Files:**
- Create: `backend/presenter.py`
- Test: `tests/test_presenter.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_presenter.py`:

```python
"""Presenter renders SearchResponse + RunContext as a sectioned terminal block.

Tests intentionally check section headers and key data presence, not exact
column widths — the presenter is allowed to evolve formatting without churning
tests, as long as the contract (3 sections, key fields visible) holds.
"""

from __future__ import annotations

from backend.pipeline.context import RunContext
from backend.presenter import render_search_result
from shared.models import (
    LiveListing,
    LivePrice,
    Recommendation,
    ScrapeMetadata,
    SearchResponse,
    Seller,
    SellerBadges,
)


def _live(item_id: str, designer: str = "Margiela", name: str = "Replica GAT") -> LiveListing:
    return LiveListing(
        id=item_id, url="https://www.grailed.com/listings/" + item_id,
        designer=designer, name=name, size="42", condition_raw="Used",
        location="US", color="white", image_urls=[],
        price=LivePrice(listing_price_usd=189, shipping_price_usd=15),
        seller=Seller(
            seller_name="s", reviews_count=1, transactions_count=1,
            items_for_sale_count=1, posted_at_unix=1700000000,
            badges=SellerBadges(verified=False, trusted_seller=False, quick_responder=False, speedy_shipper=False),
        ),
        description="",
    )


def _rec(item_id: str, *, profit: float = 122.0, p_sell: float = 0.71, conf: float = 78.0) -> Recommendation:
    return Recommendation(
        item_id=item_id, scraped_at_unix=0, query="margiela gats",
        expected_profit_grailed=profit, expected_profit_off_grailed=profit + 30.0,
        buy_cost=189.0, p_sell=p_sell, q50=342.0, confidence_pct=conf,
        valuation={"metrics": {"num_valid_time_comps": 12, "num_valid_price_comps": 14}},
        sell_probability={}, live_listing=_live(item_id),
    )


def _ctx_with_metrics() -> RunContext:
    ctx = RunContext()
    ctx.record_stage("scrape", duration_ms=6213, live_requested=40, live_returned=38, total_live_found=120)
    ctx.record_stage("value", duration_ms=1940, valued=22, no_data=14, errored=2, sold_comps_total=912, sold_comps_with_data=634)
    ctx.record_stage("rank", duration_ms=4, ranked=22)
    ctx.record_stage("persist", duration_ms=251, inserted=22)
    return ctx


def _response(item_count: int) -> SearchResponse:
    return SearchResponse(
        metadata=ScrapeMetadata(
            query="margiela gats", categories=[], live_limit_requested=40,
            sold_limit_requested=40, scraped_at_unix=0, total_live_found=120,
        ),
        items=[_rec(f"item-{i}", profit=200.0 - i, p_sell=0.5) for i in range(item_count)],
    )


def test_render_includes_three_section_headers():
    out = render_search_result(_response(2), _ctx_with_metrics(), use_color=False)
    assert "SEARCH" in out
    assert "STAGE TIMINGS" in out
    assert "TOP" in out  # "TOP 20 RESULTS"
    assert "WARNINGS" in out


def test_render_shows_query_and_run_id():
    ctx = _ctx_with_metrics()
    out = render_search_result(_response(1), ctx, use_color=False)
    assert "margiela gats" in out
    assert ctx.run_id in out


def test_render_caps_results_at_top_n():
    ctx = _ctx_with_metrics()
    out = render_search_result(_response(50), ctx, use_color=False, top_n=5)
    # Item ids item-0 .. item-4 should appear; item-5 should not.
    assert "item-0" in out
    assert "item-4" in out
    assert "item-5" not in out


def test_render_truncates_long_warnings_section():
    ctx = _ctx_with_metrics()
    for i in range(20):
        ctx.add_warning(f"no_data: id-{i} (Designer Name)")
    out = render_search_result(_response(1), ctx, use_color=False)
    # 6 visible + a "more" line
    visible = [line for line in out.splitlines() if "no_data:" in line]
    assert len(visible) <= 6
    assert "more" in out.lower()


def test_render_no_color_emits_no_ansi_escapes():
    out = render_search_result(_response(1), _ctx_with_metrics(), use_color=False)
    assert "\x1b[" not in out


def test_render_with_color_emits_ansi_escapes():
    out = render_search_result(_response(1), _ctx_with_metrics(), use_color=True)
    assert "\x1b[" in out


def test_render_empty_results_section_handled():
    ctx = RunContext()
    ctx.record_stage("scrape", duration_ms=100, live_requested=10, live_returned=0, total_live_found=0)
    ctx.record_stage("value", duration_ms=1, valued=0, no_data=0, errored=0, sold_comps_total=0, sold_comps_with_data=0)
    ctx.record_stage("rank", duration_ms=0, ranked=0)
    out = render_search_result(_response(0), ctx, use_color=False)
    assert "no rankable" in out.lower() or "0 items" in out.lower() or "(empty)" in out.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run:
```bash
pytest tests/test_presenter.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'backend.presenter'`.

- [ ] **Step 3: Create `backend/presenter.py`**

```python
"""Render a SearchResponse + RunContext as a packaged terminal block.

Three sections separated by horizontal rules:
  1. SEARCH header (query, run_id, total time)
  2. STAGE TIMINGS + LISTING FUNNEL + COMP FUNNEL
  3. TOP N RESULTS (table)
  4. WARNINGS (capped at 6 visible)

ANSI color is opt-in via ``use_color=True``. CLI passes ``sys.stdout.isatty()
and not args.no_color``.
"""

from __future__ import annotations

from shared.models import Recommendation, SearchResponse

from backend.pipeline.context import RunContext

_RULE_HEAVY = "═" * 79
_RULE_LIGHT = "─" * 79
_RULE_THIN = "─" * 28


# ANSI helpers (used only when use_color=True)
def _c(code: str, text: str, *, on: bool) -> str:
    return f"\x1b[{code}m{text}\x1b[0m" if on else text


def _green(t: str, *, on: bool) -> str:
    return _c("32", t, on=on)


def _red(t: str, *, on: bool) -> str:
    return _c("31", t, on=on)


def _yellow(t: str, *, on: bool) -> str:
    return _c("33", t, on=on)


def _money(value: float) -> str:
    return f"${int(round(value)):,}"


def _pct(value: float) -> str:
    return f"{int(round(value))}%"


def _truncate(text: str, width: int) -> str:
    if len(text) <= width:
        return text.ljust(width)
    return (text[: width - 1] + "…").ljust(width)


def _header(query: str, run_id: str, total_ms: int) -> str:
    return "\n".join(
        [
            _RULE_HEAVY,
            f"  SEARCH  query={query!r}  run_id={run_id}  total={total_ms / 1000:.1f}s",
            _RULE_HEAVY,
        ]
    )


def _stage_block(ctx: RunContext) -> str:
    timings = ctx.timings_ms
    counts = ctx.counts
    rows_left = [
        ("scrape ", timings.get("scrape", 0)),
        ("value  ", timings.get("value", 0)),
        ("rank   ", timings.get("rank", 0)),
        ("persist", timings.get("persist", 0)),
        ("total  ", ctx.total_ms),
    ]
    rows_right = [
        ("live requested  ", counts.get("scrape.live_requested", 0)),
        ("live returned   ", counts.get("scrape.live_returned", 0)),
        ("valued          ", counts.get("value.valued", 0)),
        ("no_data         ", counts.get("value.no_data", 0)),
        ("errored         ", counts.get("value.errored", 0)),
    ]
    lines: list[str] = []
    lines.append("  STAGE TIMINGS                       LISTING FUNNEL")
    lines.append(f"  {_RULE_THIN}          {_RULE_THIN}")
    for (lname, lval), (rname, rval) in zip(rows_left, rows_right + [("", 0)] * 5):
        left = f"{lname}    {lval:>8,} ms"
        right = f"{rname} {rval:>5}" if rname else ""
        lines.append(f"  {left:<38}{right}")
    lines.append("")
    lines.append("  COMP FUNNEL")
    lines.append(f"  {_RULE_THIN}")
    total = counts.get("value.sold_comps_total", 0)
    with_data = counts.get("value.sold_comps_with_data", 0)
    pct = (with_data / total * 100) if total else 0.0
    lines.append(f"  sold comps total       {total:>5}")
    lines.append(f"  sold comps with data   {with_data:>5}   ({pct:.1f}%)")
    return "\n".join(lines)


def _results_block(items: list[Recommendation], top_n: int, *, use_color: bool) -> str:
    if not items:
        return "\n".join([_RULE_LIGHT, "  TOP RESULTS", _RULE_LIGHT, "", "  (empty — 0 items ranked)"])
    head = "\n".join(
        [
            _RULE_LIGHT,
            f"  TOP {top_n} RESULTS  ranked by p_sell × expected_profit_grailed",
            _RULE_LIGHT,
            "",
            "  #    designer / name                          buy     q50    profit    off    p_sell  conf  comps",
            "  ───  ───────────────────────────────────────  ──────  ──────  ───────  ──────  ──────  ────  ─────",
        ]
    )
    body_lines: list[str] = []
    for idx, rec in enumerate(items[:top_n], start=1):
        title = _truncate(f"{rec.live_listing.designer} / {rec.live_listing.name}", 39)
        comps_metrics = rec.valuation.get("metrics", {}) if isinstance(rec.valuation, dict) else {}
        valid_time = comps_metrics.get("num_valid_time_comps", 0)
        valid_price = comps_metrics.get("num_valid_price_comps", 0)
        comps = f"{valid_time}/{valid_price}"

        profit_str = _money(rec.expected_profit_grailed)
        if use_color:
            profit_str = _green(profit_str, on=True) if rec.expected_profit_grailed >= 0 else _red(profit_str, on=True)
        off_str = _money(rec.expected_profit_off_grailed)

        conf_str = _pct(rec.confidence_pct)
        if use_color:
            if rec.confidence_pct >= 75:
                conf_str = _green(conf_str, on=True)
            elif rec.confidence_pct >= 50:
                conf_str = _yellow(conf_str, on=True)
            else:
                conf_str = _red(conf_str, on=True)

        body_lines.append(
            f"  {idx:>3}  {title}  {_money(rec.buy_cost):>6}  {_money(rec.q50):>6}  "
            f"{profit_str:>7}  {off_str:>6}  {rec.p_sell:>6.2f}  {conf_str:>4}  {comps:>5}"
        )
    return head + "\n" + "\n".join(body_lines)


def _warnings_block(warnings: list[str]) -> str:
    head = "\n".join([_RULE_LIGHT, f"  WARNINGS  ({len(warnings)})", _RULE_LIGHT, ""])
    if not warnings:
        return head + "  (none)"
    visible = warnings[:6]
    body = "\n".join(f"  {w}" for w in visible)
    if len(warnings) > 6:
        body += f"\n  ({len(warnings) - 6} more — pass --json for full list)"
    return head + body


def render_search_result(
    response: SearchResponse,
    ctx: RunContext,
    *,
    top_n: int = 20,
    use_color: bool = False,
) -> str:
    parts = [
        _header(response.metadata.query, ctx.run_id, ctx.total_ms),
        "",
        _stage_block(ctx),
        "",
        _results_block(response.items, top_n=top_n, use_color=use_color),
        "",
        _warnings_block(ctx.warnings),
        "",
        _RULE_HEAVY,
    ]
    return "\n".join(parts)
```

- [ ] **Step 4: Run tests to verify pass**

Run:
```bash
pytest tests/test_presenter.py -v
```
Expected: PASS (7 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/presenter.py tests/test_presenter.py
git commit -m "feat(presenter): add packaged CLI presenter for SearchResponse"
```

---

## Task 13: Rewrite `backend/cli.py` with positional args

**Files:**
- Modify: `backend/cli.py`
- Test: `tests/test_backend_cli_smoke.py` (replace)

- [ ] **Step 1: Inspect the current cli smoke test**

Run:
```bash
cat tests/test_backend_cli_smoke.py
```

- [ ] **Step 2: Replace `tests/test_backend_cli_smoke.py` with the new failing tests**

```python
"""CLI uses positional args: search <query> <live_limit> <sold_limit>."""

from __future__ import annotations

import asyncio
import json
import sys

import pytest

from backend import cli as backend_cli
from backend.pipeline import search as pipeline_search
from shared.models import (
    LiveListing, LivePrice, Recommendation, ScrapeMetadata,
    SearchParams, SearchResponse, Seller, SellerBadges,
)


def _live(item_id: str = "abc") -> LiveListing:
    return LiveListing(
        id=item_id, url="https://www.grailed.com/listings/" + item_id,
        designer="Margiela", name="Replica GAT", size="42",
        condition_raw="Used", location="US", color="white", image_urls=[],
        price=LivePrice(listing_price_usd=189, shipping_price_usd=15),
        seller=Seller(
            seller_name="s", reviews_count=1, transactions_count=1,
            items_for_sale_count=1, posted_at_unix=0,
            badges=SellerBadges(verified=False, trusted_seller=False, quick_responder=False, speedy_shipper=False),
        ),
        description="",
    )


def _response() -> SearchResponse:
    return SearchResponse(
        metadata=ScrapeMetadata(
            query="margiela gats", categories=[], live_limit_requested=40,
            sold_limit_requested=40, scraped_at_unix=0, total_live_found=2,
        ),
        items=[
            Recommendation(
                item_id="abc", scraped_at_unix=0, query="margiela gats",
                expected_profit_grailed=122.0, expected_profit_off_grailed=153.0,
                buy_cost=189.0, p_sell=0.71, q50=342.0, confidence_pct=78.0,
                valuation={"metrics": {"num_valid_time_comps": 12, "num_valid_price_comps": 14}},
                sell_probability={}, live_listing=_live(),
            )
        ],
    )


def test_search_positional_args_invokes_run_search(monkeypatch, capsys):
    captured = {}

    async def _run(params, ctx, *, persist=True):
        captured["params"] = params
        captured["persist"] = persist
        return _response()

    monkeypatch.setattr(backend_cli, "run_search", _run)
    monkeypatch.setattr(backend_cli, "_wire_stores", lambda: None)

    rc = backend_cli.main(["search", "margiela gats", "40", "40", "--no-persist"])
    assert rc == 0
    assert captured["params"].query == "margiela gats"
    assert captured["params"].live_limit == 40
    assert captured["params"].sold_limit == 40
    assert captured["persist"] is False

    out = capsys.readouterr().out
    assert "SEARCH" in out
    assert "TOP" in out


def test_search_json_flag_emits_valid_json(monkeypatch, capsys):
    async def _run(params, ctx, *, persist=True):
        return _response()

    monkeypatch.setattr(backend_cli, "run_search", _run)
    monkeypatch.setattr(backend_cli, "_wire_stores", lambda: None)

    rc = backend_cli.main(["search", "guidi", "5", "5", "--no-persist", "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["items"][0]["expected_profit_grailed"] == 122.0
    assert "edge_usd" not in parsed["items"][0]


def test_search_persist_default_wires_stores(monkeypatch):
    wired = []

    async def _run(params, ctx, *, persist=True):
        return _response()

    monkeypatch.setattr(backend_cli, "run_search", _run)
    monkeypatch.setattr(backend_cli, "_wire_stores", lambda: wired.append(True))

    backend_cli.main(["search", "guidi", "5", "5"])
    assert wired == [True]


def test_search_no_persist_skips_store_wiring(monkeypatch):
    wired = []

    async def _run(params, ctx, *, persist=True):
        return _response()

    monkeypatch.setattr(backend_cli, "run_search", _run)
    monkeypatch.setattr(backend_cli, "_wire_stores", lambda: wired.append(True))

    backend_cli.main(["search", "guidi", "5", "5", "--no-persist"])
    assert wired == []


def test_argparse_rejects_non_int_limits(capsys):
    with pytest.raises(SystemExit):
        backend_cli.main(["search", "guidi", "abc", "5"])
```

- [ ] **Step 3: Run tests to verify they fail**

Run:
```bash
pytest tests/test_backend_cli_smoke.py -v
```
Expected: FAIL — old CLI uses interactive prompts, new tests use positional args.

- [ ] **Step 4: Replace `backend/cli.py`**

```python
"""CLI test harness for the backend search pipeline.

Usage:
  python -m backend.cli search <query> <live_limit> <sold_limit> [--no-persist] [--json] [--no-color]

Examples:
  python -m backend.cli search "margiela gats" 40 40
  python -m backend.cli search guidi 20 30 --no-persist
  python -m backend.cli search "carol christian poell" 10 10 --json | jq

This file contains zero business logic. It builds a RunContext, calls
run_search, and either prints the presenter block or dumps JSON.
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
    parser = argparse.ArgumentParser(prog="backend.cli", description="CLI for backend search pipeline")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="Run a search")
    s.add_argument("query", help="Search query (quote multi-word)")
    s.add_argument("live_limit", type=int, help="Number of active listings to fetch")
    s.add_argument("sold_limit", type=int, help="Number of sold comparables per active listing")
    s.add_argument("--no-persist", action="store_true", help="Skip persisting recommendations to Supabase")
    s.add_argument("--json", action="store_true", help="Emit JSON instead of presenter output")
    s.add_argument("--no-color", action="store_true", help="Disable ANSI colors in presenter output")
    return parser


def _wire_stores() -> None:
    """Wire the ListingStore for scraper + EV + recommendations. Mirrors
    backend.main:lifespan so the CLI can persist."""
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
    args = _build_parser().parse_args(argv)
    if args.command != "search":
        return 1

    configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
    persist = not args.no_persist
    if persist:
        _wire_stores()

    params = SearchParams(query=args.query, live_limit=args.live_limit, sold_limit=args.sold_limit)
    ctx = RunContext()

    try:
        response = asyncio.run(run_search(params, ctx, persist=persist))
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(response.model_dump_json(indent=2))
    else:
        use_color = (not args.no_color) and sys.stdout.isatty()
        print(render_search_result(response, ctx, use_color=use_color))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 5: Run tests to verify pass**

Run:
```bash
pytest tests/test_backend_cli_smoke.py -v
```
Expected: PASS (5 passed).

- [ ] **Step 6: Commit**

```bash
git add backend/cli.py tests/test_backend_cli_smoke.py
git commit -m "refactor(cli): positional-arg CLI with packaged presenter output"
```

---

## Task 14: Run the full test suite and fix any cross-test breakage

**Files:** none (validation step)

- [ ] **Step 1: Run the entire suite**

Run:
```bash
pytest -q
```
Expected: all tests pass. Likely failure modes:
- Lingering imports of deleted models in other test files — fix by editing the offending test.
- Lingering imports from `backend.orchestrator` — same.
- `tests/test_ev_*` should be unaffected (they import from `ev.*`).

- [ ] **Step 2: If any tests fail, list them and fix one at a time**

For each failing test: read, decide whether the test still asserts a useful behavior, and either fix or delete. Commit each fix separately:

```bash
git add <files>
git commit -m "test: <one-line fix description>"
```

- [ ] **Step 3: Confirm green suite**

Run:
```bash
pytest -q
```
Expected: all green.

---

## Task 15: Documentation — archive agent SSE spec, add placeholder, update README

**Files:**
- Move: `docs/2026-04-25-agent-run-sse-spec.md` → `docs/archive/2026-04-25-agent-run-sse-spec.md`
- Create: `docs/agent-flow-future.md`
- Modify: `README.md`
- Modify: `docs/2026-04-25-rest-api-and-ev-persistence-design.md`
- Modify: `.env.example`

- [ ] **Step 1: Create archive directory and move the agent spec**

Run:
```bash
mkdir -p docs/archive
git mv docs/2026-04-25-agent-run-sse-spec.md docs/archive/2026-04-25-agent-run-sse-spec.md
```

- [ ] **Step 2: Prepend an archived banner to the moved file**

Open `docs/archive/2026-04-25-agent-run-sse-spec.md`. Insert at the very top (line 1), before the existing `# Agent Run SSE Spec`:

```markdown
> **Archived 2026-04-26** with the backend orchestration rewrite. The agent
> flow has been removed; a future rebuild will live on its own branch and
> will not necessarily follow this contract. Kept for historical reference.

```

- [ ] **Step 3: Create `docs/agent-flow-future.md`**

```markdown
# Agent Flow — Future Work

The previous agent flow (`POST /agent/run`) was removed on 2026-04-26 with
the backend orchestration rewrite. Reasons:

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
- SSE event model reduced to 3-4 types (`stage_started`, `stage_completed`,
  `result`, `done`).

Archived design: [docs/archive/2026-04-25-agent-run-sse-spec.md](archive/2026-04-25-agent-run-sse-spec.md).
```

- [ ] **Step 4: Add a superseded banner to the rest-api spec**

Open `docs/2026-04-25-rest-api-and-ev-persistence-design.md`. Insert at the very top (line 1):

```markdown
> **Status (2026-04-26):** partially superseded by
> [backend orchestration rewrite design](superpowers/specs/2026-04-26-backend-orchestration-rewrite-design.md).
> Field names changed (`edge_usd`/`cost`/`confidence` → `expected_profit_grailed`/`buy_cost`/`confidence_pct`).
> Endpoint surface trimmed to `/health`, `/search`, `/recommendations`.

```

- [ ] **Step 5: Rewrite the README**

Replace the entire `README.md` with:

```markdown
# code-brown — backend handoff

Grailed arbitrage finder. This README is the handoff doc for the rest of the team to run the backend locally and call its endpoints.

For project context, see [docs/SPEC.md](docs/SPEC.md). For the rewrite spec, see [docs/superpowers/specs/2026-04-26-backend-orchestration-rewrite-design.md](docs/superpowers/specs/2026-04-26-backend-orchestration-rewrite-design.md).

---

## 1. Quick start

Requires Python 3.10+.

```bash
# from repo root
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

cp .env.example .env               # then fill it in — see §2
uvicorn backend.main:app --reload --port 8000
```

The server boots if `API_KEY`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` are all set and non-empty. Missing any of them and `lifespan` raises on startup — intentional.

Sanity check:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

OpenAPI docs auto-generate at `http://localhost:8000/docs`.

Logs are JSON-line by default. For human-readable output during dev:
```bash
LOG_FORMAT=text uvicorn backend.main:app --reload --port 8000
```

---

## 2. Environment variables

Each dev runs their own backend on `localhost`. **Do not commit `.env`** — gitignored.

| Variable                    | Required | What it is                                                                                                                 |
| --------------------------- | -------- | -------------------------------------------------------------------------------------------------------------------------- |
| `API_KEY`                   | yes      | Bearer token clients send. Pick anything random, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`.       |
| `SUPABASE_URL`              | yes      | Your Supabase project URL (e.g. `https://xxxx.supabase.co`).                                                                |
| `SUPABASE_SERVICE_ROLE_KEY` | yes      | Service role key from the same project. Server-side only.                                                                   |
| `ALGOLIA_API_KEY`           | yes      | Grailed's public Algolia search key (Network tab on a search request).                                                      |
| `LOG_FORMAT`                | no       | `json` (default) or `text`. Text format is grep-friendly key=value lines.                                                   |
| `LOG_LEVEL`                 | no       | `INFO` (default), `DEBUG`, `WARNING`, etc.                                                                                  |

Your Supabase project needs the migrations in `supabase/migrations/` applied — `listings` and `recommendations` tables plus the `list_latest_recommendations` RPC. Run them via the Supabase SQL editor or `supabase db push`.

---

## 3. API reference

All endpoints except `/health` require `Authorization: Bearer $API_KEY`. Missing/wrong token → `401`.

Request and response bodies are Pydantic models in [shared/models.py](shared/models.py).

### `GET /health`

Public. `{"status":"ok"}`. Use for uptime checks.

### `POST /search`

Scrape Grailed for active listings, value each one against sold comparables, rank by `p_sell × expected_profit_grailed`, persist, return ranked list.

**Request body** — `SearchParams`. Only `query` is meaningful as a default.

```json
{
  "query": "margiela gats",
  "department": "menswear",
  "category": "footwear",
  "min_price_usd": 0,
  "max_price_usd": 1000000,
  "live_limit": 40,
  "sold_limit": 40,
  "include_sold": true
}
```

**Response** — `SearchResponse` with `metadata` and `items: list[Recommendation]`.

```bash
curl -X POST http://localhost:8000/search \
  -H "Authorization: Bearer $API_KEY" \
  -H "content-type: application/json" \
  -d '{"query":"margiela gats","live_limit":10,"sold_limit":10}'
```

Expect 5–30s latency.

### `GET /recommendations`

Latest persisted recommendation per listing identity, sorted by `expected_profit_grailed` desc. No scraping. Useful for warming up a UI.

**Query params:** `limit` (1–200, default 50).

**Response** — `{"items": [Recommendation, ...]}`.

```bash
curl "http://localhost:8000/recommendations?limit=20" \
  -H "Authorization: Bearer $API_KEY"
```

---

## 4. The `Recommendation` shape

One ranked listing. Returned by both `/search` (inside `items`) and `/recommendations`. Single shape so the frontend writes one renderer.

Top-level typed fields you can sort/filter/display directly:

- `item_id`, `query`, `scraped_at_unix`
- `expected_profit_grailed` — primary rank metric (q50 net of Grailed fees minus `buy_cost`)
- `expected_profit_off_grailed` — secondary (q50 minus `buy_cost`)
- `buy_cost` — true acquisition cost (listing + NYC sales tax + shipping)
- `p_sell` — probability the item sells in the horizon
- `q50` — median expected sale price (weighted)
- `confidence_pct` — 0–100 numeric confidence in the valuation
- `live_listing` — full `LiveListing`

Two opaque dicts whose internals will grow:

- `valuation` — full EV math output (see [ev/EV_MODEL_SPEC.md](ev/EV_MODEL_SPEC.md) §3.4)
- `sell_probability` — sell-time math (see [ev/EV_MODEL_SPEC.md](ev/EV_MODEL_SPEC.md) §4)

**Render rule:** read what you know about; ignore unknown keys. The math owner adds fields; nothing renamed/removed.

---

## 5. What's stable, what's not

Stable — depend on these:

- The three endpoints, their auth, request/response shapes.
- Top-level typed fields on `Recommendation`.
- Existing keys inside `valuation` / `sell_probability` (additive-only).

Not stable — **don't build against and don't modify**:

- `scraper/`, `ev/` internals — changing.
- The Supabase schema beyond what's in `supabase/migrations/`.

If you need a new endpoint/field/behavior: ping Oliver. Don't add it inline.

---

## 6. Troubleshooting

`RuntimeError: API_KEY environment variable must be set` on startup → `.env` not loaded or value empty. Confirm running from repo root.

`401 Unauthorized` → missing `Authorization: Bearer …` header or token mismatch.

Supabase errors on `/search` or `/recommendations` → migrations not applied, or service role key is the anon key.

`/search` slow → real network calls (Grailed + Algolia). 5–30s normal. >60s = rate limit.

---

## 7. CLI

For driving the pipeline without HTTP:

```bash
python -m backend.cli search "<query>" <live_limit> <sold_limit> [--no-persist] [--json] [--no-color]
```

Examples:

```bash
python -m backend.cli search "margiela gats" 40 40
python -m backend.cli search guidi 20 30 --no-persist
python -m backend.cli search "carol christian poell" 10 10 --json | jq
```

Output is a packaged terminal block with three sections:

```
═══════════════════════════════════════════════════════════════════════════════
  SEARCH  query='margiela gats'  run_id=a1b2c3d4e5f6  total=8.4s
═══════════════════════════════════════════════════════════════════════════════

  STAGE TIMINGS                       LISTING FUNNEL
  ─────────────────────────           ────────────────────────────
  scrape         6,213 ms              live requested      40
  value          1,940 ms              live returned       38
  rank               4 ms              valued              22
  persist          251 ms              no_data             14
  total          8,408 ms              errored              2

  COMP FUNNEL
  ─────────────────────────
  sold comps total          912
  sold comps with data      634   (69.5%)


───────────────────────────────────────────────────────────────────────────────
  TOP 20 RESULTS  ranked by p_sell × expected_profit_grailed
───────────────────────────────────────────────────────────────────────────────
  ...
```

`--no-persist` skips Supabase. `--json` dumps the raw response (skips presenter). `--no-color` disables ANSI even on a TTY.

---

## 8. Future work

The agent flow (`POST /agent/run`) and `/hype/{term}` were removed on 2026-04-26. See [docs/agent-flow-future.md](docs/agent-flow-future.md) for the rebuild plan.
```

- [ ] **Step 6: Update `.env.example`**

Replace contents:

```env
# Bearer token clients send as `Authorization: Bearer <value>`.
# Pick anything random: `python -c "import secrets; print(secrets.token_urlsafe(32))"`
API_KEY=

# Your own Supabase dev project. URL + service-role key (the long one in API settings).
# Migrations in supabase/migrations/ must be applied to this project.
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=

# Grailed's public Algolia search key. Grab from a Grailed search request in the Network tab.
ALGOLIA_API_KEY=

# Optional logging knobs.
# LOG_FORMAT=text     # 'json' (default) or 'text' for grep-friendly key=value
# LOG_LEVEL=INFO      # DEBUG | INFO | WARNING | ERROR
```

- [ ] **Step 7: Verify file changes**

Run:
```bash
git status
```
Expected: rename `docs/2026-04-25-agent-run-sse-spec.md` → `docs/archive/...`, modified `README.md`, modified `docs/2026-04-25-rest-api-and-ev-persistence-design.md`, modified `.env.example`, new `docs/agent-flow-future.md`.

- [ ] **Step 8: Commit**

```bash
git add docs/archive/ docs/agent-flow-future.md docs/2026-04-25-rest-api-and-ev-persistence-design.md README.md .env.example
git commit -m "docs: rewrite README, archive agent spec, add future-flow placeholder"
```

---

## Task 16: Manual integration smoke test

**Files:** none (validation)

- [ ] **Step 1: Confirm `.env` is populated and dev DB has the new migration applied**

Run:
```bash
cat .env | grep -v '^#'
ls -1 supabase/migrations/ | sort | tail -1
```
Expected: env values non-empty; latest migration is `20260426120000_recs_use_grailed_profit.sql`.

- [ ] **Step 2: CLI happy path with persistence**

Run:
```bash
python -m backend.cli search "margiela gats" 10 10
```
Expected: presenter block prints in 8–30s with three sections. `STAGE TIMINGS` shows non-zero values for all four stages including `persist`. Top results table shows `expected_profit_grailed` and `confidence_pct`.

- [ ] **Step 3: CLI with `--no-persist --json`**

Run:
```bash
python -m backend.cli search guidi 5 5 --no-persist --json | python -c "import json, sys; d=json.load(sys.stdin); print('ok' if all(k in d['items'][0] for k in ['expected_profit_grailed','buy_cost','confidence_pct']) else 'BAD')"
```
Expected: `ok`. (If no items return for `guidi`, try `margiela`.)

- [ ] **Step 4: Verify legacy fields are gone from JSON**

Run:
```bash
python -m backend.cli search guidi 3 3 --no-persist --json | python -c "import json,sys; d=json.load(sys.stdin); item=d['items'][0]; assert 'edge_usd' not in item and 'cost' not in item and 'confidence' not in item; print('legacy fields confirmed absent')"
```
Expected: `legacy fields confirmed absent`.

- [ ] **Step 5: Test `LOG_FORMAT=text`**

Run:
```bash
LOG_FORMAT=text python -m backend.cli search guidi 3 3 --no-persist 2>&1 | head -20
```
Expected: see human-readable lines like `2026-04-26T... INFO  backend run_id=...  msg='run_started'`.

- [ ] **Step 6: HTTP server smoke**

In one terminal:
```bash
uvicorn backend.main:app --reload --port 8000
```

In another:
```bash
curl -sX POST http://localhost:8000/search \
  -H "Authorization: Bearer $(grep API_KEY .env | cut -d= -f2)" \
  -H "content-type: application/json" \
  -d '{"query":"guidi","live_limit":3,"sold_limit":3}' | python -m json.tool | head -40

curl -s "http://localhost:8000/recommendations?limit=5" \
  -H "Authorization: Bearer $(grep API_KEY .env | cut -d= -f2)" | python -m json.tool | head -30

curl -s -o /dev/null -w "%{http_code}\n" "http://localhost:8000/hype/guidi" \
  -H "Authorization: Bearer $(grep API_KEY .env | cut -d= -f2)"
# Expected: 404

curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://localhost:8000/agent/run" \
  -H "Authorization: Bearer $(grep API_KEY .env | cut -d= -f2)" \
  -H "content-type: application/json" -d '{"intent_text":"x"}'
# Expected: 404
```

Stop the uvicorn process.

- [ ] **Step 7: All-green pytest**

Run:
```bash
pytest -q
```
Expected: all tests pass.

- [ ] **Step 8: Commit any small fixes from manual testing as separate commits**

If anything broke, fix it and commit each fix with a focused message before merging.

---

## Task 17: Push and prepare PR

**Files:** none

- [ ] **Step 1: Confirm clean working tree on `backend-rewrite`**

Run:
```bash
git status
git log --oneline backend..backend-rewrite | head -30
```
Expected: clean tree; commit history shows the tasks above (one commit per task or split-task).

- [ ] **Step 2: Push the branch**

Run:
```bash
git push -u origin backend-rewrite
```

- [ ] **Step 3: Open PR**

Use `gh pr create` per the standard template. The summary should mention:
- Removed `/agent/run`, `/hype/{term}`; deleted `backend/agent/`.
- Reshaped `Recommendation` around EV's new fields.
- New `backend/pipeline/` with `RunContext` + named stages, structured logging.
- New positional-arg CLI with packaged presenter.
- New Supabase migration; **must be applied before merging**.
- Known follow-ups: `frontend/` and `agent-ui/` will need updates (out of this PR's scope, see spec §15).

---

## Self-Review

**Spec coverage check:**

| Spec section | Covered by |
|---|---|
| §2 In scope: agent dir delete | Task 3 |
| §2 In scope: orchestrator delete | Task 4 |
| §2 In scope: Recommendation reshape | Task 1 |
| §2 In scope: agent + hype model deletion | Task 2 |
| §2 In scope: Supabase migration | Task 10 |
| §2 In scope: store update | Task 9 |
| §2 In scope: structured logging | Task 6 |
| §2 In scope: pipeline/ + context.py + search.py | Tasks 5, 7 |
| §2 In scope: presenter | Task 12 |
| §2 In scope: CLI rewrite | Task 13 |
| §2 In scope: README | Task 15 |
| §2 In scope: archive agent SSE spec | Task 15 |
| §2 In scope: agent-flow-future.md placeholder | Task 15 |
| §5.1 New Recommendation shape | Task 1 |
| §5.2 New ranking formula | Tasks 7, 11 (RPC in Task 10) |
| §5.4 Migration | Task 10 |
| §5.5 Store change | Task 9 |
| §6 RunContext | Task 5 |
| §7 Logging setup | Task 6 |
| §8 Pipeline stages + run_search | Task 7 (split a/b/c) |
| §9 Presenter | Task 12 |
| §10 CLI | Task 13 |
| §11 FastAPI surface | Task 11 |
| §12 Documentation | Task 15 |
| §13 Tests | Tasks 1, 5, 6, 7, 9, 11, 12, 13 each include tests |
| §14 Manual integration | Task 16 |
| §15 Known UI impact (out-of-scope) | Documented in PR summary, Task 17 |

No gaps.

**Placeholder scan:** none. Every code step shows complete code; every command shows expected output where it's checkable.

**Type/name consistency:**
- `RunContext.record_stage` signature uses keyword-only `duration_ms` and `**counts` — matches in both `context.py` (Task 5) and all stage call sites (Task 7).
- `Recommendation` field names (`expected_profit_grailed`, etc.) match across tests, model, store, presenter, and migration.
- `pipeline_search` is the test-side alias for `backend.pipeline.search` — used consistently.
- `run_search(params, ctx, *, persist=True)` signature matches its callers in `main.py` and `cli.py`.
- `render_search_result(response, ctx, *, top_n=20, use_color=False)` — matches caller in CLI.

All consistent.

---

## Execution Handoff

Plan complete and saved to [docs/superpowers/plans/2026-04-26-backend-orchestration-rewrite.md](docs/superpowers/plans/2026-04-26-backend-orchestration-rewrite.md).

**Two execution options:**

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session using executing-plans, batch with checkpoints.

Which approach?
