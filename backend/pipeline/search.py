"""Search pipeline.

Public surface: ``run_search``. Stages are private helpers.
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
        except Exception as exc:  # noqa: BLE001
            errored += 1
            ctx.logger.warning(
                "value_row_errored",
                extra={"stage": "value", "item_id": row.live_listing.id, "error": str(exc)},
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
            metrics = valuation.get("metrics", {})
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
            sold_comps_with_data += int(metrics.get("num_valid_time_comps", 0))
            items.append(rec)
        except Exception as exc:  # noqa: BLE001
            errored += 1
            ctx.logger.warning(
                "value_row_shape_mismatch",
                extra={"stage": "value", "item_id": row.live_listing.id, "error": str(exc)},
            )

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
            "sold_comps_total": sold_comps_total,
            "sold_comps_with_data": sold_comps_with_data,
        },
    )
    return items


def _rank_stage(items: list[Recommendation], ctx: RunContext) -> list[Recommendation]:
    ctx.logger.info("stage_started", extra={"stage": "rank"})
    started = monotonic()
    ranked = sorted(
        items,
        key=lambda item: item.p_sell * item.expected_profit_grailed,
        reverse=True,
    )
    duration_ms = int((monotonic() - started) * 1000)
    ctx.record_stage("rank", duration_ms=duration_ms, ranked=len(ranked))
    ctx.logger.info(
        "stage_completed",
        extra={"stage": "rank", "duration_ms": duration_ms, "ranked": len(ranked)},
    )
    return ranked


async def _scrape_stage(params: SearchParams, ctx: RunContext) -> GrailedScrapeResult:
    ctx.logger.info("stage_started", extra={"stage": "scrape"})
    started = monotonic()
    scrape_result = await scrape(params, persist=False)
    duration_ms = int((monotonic() - started) * 1000)
    ctx.record_stage(
        "scrape",
        duration_ms=duration_ms,
        live_requested=params.live_limit,
        live_returned=len(scrape_result.results),
        total_live_found=scrape_result.metadata.total_live_found,
    )
    ctx.logger.info(
        "stage_completed",
        extra={
            "stage": "scrape",
            "duration_ms": duration_ms,
            "live_requested": params.live_limit,
            "live_returned": len(scrape_result.results),
            "total_live_found": scrape_result.metadata.total_live_found,
        },
    )
    return scrape_result


def _persist_stage(response: SearchResponse, params: SearchParams, ctx: RunContext) -> None:
    ctx.logger.info("stage_started", extra={"stage": "persist"})
    started = monotonic()
    inserted = 0
    store = get_recommendations_store()
    if store is None:
        ctx.add_warning("persist skipped: recommendations store is not configured")
    else:
        try:
            store.save_recommendations(response=response, params=params)
            inserted = len(response.items)
        except Exception as exc:  # noqa: BLE001
            ctx.logger.error(
                "persist_failed",
                extra={"stage": "persist", "error": str(exc)},
            )
            ctx.add_warning(f"persist failed: {exc}")
    duration_ms = int((monotonic() - started) * 1000)
    ctx.record_stage("persist", duration_ms=duration_ms, inserted=inserted)
    ctx.logger.info(
        "stage_completed",
        extra={"stage": "persist", "duration_ms": duration_ms, "inserted": inserted},
    )


async def run_search(params: SearchParams, ctx: RunContext, *, persist: bool = True) -> SearchResponse:
    ctx.logger.info(
        "run_started",
        extra={"query": params.query, "live_limit": params.live_limit, "sold_limit": params.sold_limit},
    )
    scrape_result = await _scrape_stage(params, ctx)
    items = _value_stage(scrape_result, params, ctx)
    ranked = _rank_stage(items, ctx)
    response = SearchResponse(metadata=scrape_result.metadata, items=ranked)
    if persist:
        _persist_stage(response, params, ctx)
    ctx.logger.info("run_completed", extra={"total_ms": ctx.total_ms, **ctx.counts})
    return response
