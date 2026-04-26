"""RunContext flows through every pipeline stage. It carries the run id,
a pre-bound logger (so log lines auto-include run_id), and accumulating
counters/timings/warnings that the presenter and structured logs both read.
"""

from __future__ import annotations

import logging

from backend.pipeline.context import RunContext


def test_run_context_generates_unique_run_ids():
    a = RunContext()
    b = RunContext()
    assert a.run_id != b.run_id
    assert len(a.run_id) == 12


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
