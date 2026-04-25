"""Wires scrape/hype flows and agent streaming run."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from time import monotonic

from backend.agent.intent import expand_intent_candidates
from backend.agent.planner import stream_plan
from backend.agent.summary import stream_summary
from ev import estimate_sell_probability, value_listing
from hype import related, score, trends
from scraper.scraper import scrape
from shared.models import (
    AgentPlan,
    AgentRunState,
    CandidateQuery,
    HypeEvidence,
    HypeProbeResult,
    HypeResult,
    Recommendation,
    SearchParams,
    SearchResponse,
)
from shared.store import get_recommendations_store


async def run_search(
    params: SearchParams,
    *,
    persist: bool = True,
    surface_no_data: bool = False,
) -> SearchResponse:
    """Run scrape + valuation + ranking.

    ``surface_no_data=True`` emits Recommendations even when the valuation
    pipeline returns no_data (no usable sold comps), with neutral metrics so
    the agent UI can still display the live listing. Persistence still skips
    no_data rows so /recommendations stays clean.
    """
    scrape_result = await scrape(params, persist=persist)
    scraped_at = scrape_result.metadata.scraped_at_unix
    items: list[Recommendation] = []
    no_data_items: list[Recommendation] = []
    for row in scrape_result.results:
        row_dict = row.model_dump(mode="json")
        valuation = value_listing(row_dict, scraped_at)
        sell_prob = estimate_sell_probability(row_dict)
        if valuation.get("status") == "no_data":
            if surface_no_data:
                live_total = (
                    row.live_listing.price.listing_price_usd
                    + row.live_listing.price.shipping_price_usd
                )
                no_data_items.append(
                    Recommendation(
                        item_id=row.live_listing.id,
                        scraped_at_unix=scraped_at,
                        query=params.query,
                        edge_usd=0.0,
                        p_sell=sell_prob["p_sell"],
                        q50=0.0,
                        cost=float(live_total),
                        confidence="no_data",
                        valuation=valuation,
                        sell_probability=sell_prob,
                        live_listing=row.live_listing,
                    )
                )
            continue
        metrics = valuation["metrics"]
        items.append(
            Recommendation(
                item_id=row.live_listing.id,
                scraped_at_unix=scraped_at,
                query=params.query,
                edge_usd=metrics["edge_usd"],
                p_sell=sell_prob["p_sell"],
                q50=valuation["dist"]["q50"],
                cost=valuation["cost"],
                confidence=_normalize_confidence(metrics),
                valuation=valuation,
                sell_probability=sell_prob,
                live_listing=row.live_listing,
            )
        )
    items.sort(key=lambda r: r.p_sell * r.edge_usd, reverse=True)
    if surface_no_data:
        no_data_items.sort(key=lambda r: r.p_sell, reverse=True)
        items = items + no_data_items
    response = SearchResponse(metadata=scrape_result.metadata, items=items)
    if persist:
        store = get_recommendations_store()
        if store is not None:
            valued_only = SearchResponse(
                metadata=scrape_result.metadata,
                items=[r for r in items if r.confidence != "no_data"],
            )
            store.save_recommendations(response=valued_only, params=params)
    return response


async def run_hype(term: str) -> HypeResult:
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


async def run_agent_stream(
    *,
    intent_text: str,
    seed_params: SearchParams | None = None,
    per_hype_timeout_s: float = 15.0,
    per_search_timeout_s: float = 90.0,
    whole_run_timeout_s: float = 240.0,
):
    started = monotonic()
    if seed_params is not None:
        intent_reasoning = "Used provided seed_params bypass."
        candidates = [CandidateQuery(query=seed_params.query, why="seed_params bypass")]
    else:
        try:
            intent_reasoning, candidates = await expand_intent_candidates(intent_text, n=6)
        except Exception as exc:
            yield {"type": "error", "stage": "intent", "message": str(exc)}
            yield {"type": "done", "total_duration_ms": int((monotonic() - started) * 1000), "queries_run": 0, "queries_failed": 0, "total_items": 0}
            return

    yield {"type": "intent_parsed", "reasoning": intent_reasoning, "candidates": [c.model_dump(mode="json") for c in candidates]}
    yield {"type": "candidates_generated", "candidates": [c.model_dump(mode="json") for c in candidates]}

    hype_results: dict[str, HypeProbeResult] = {}
    hype_errors: list[dict] = []
    hype_semaphore = asyncio.Semaphore(4)

    async def _probe(query_text: str):
        async with hype_semaphore:
            try:
                result = await asyncio.wait_for(run_hype(query_text), timeout=per_hype_timeout_s)
                momentum = 0
                if result.series_7d and result.series_7d.points and result.series_90d and result.series_90d.points:
                    momentum = int(result.series_7d.points[-1].intensity - result.series_90d.points[-1].intensity)
                return HypeProbeResult(
                    query=query_text,
                    score=result.score,
                    confidence=result.confidence,
                    momentum_pct=momentum,
                    related=result.evidence.related,
                )
            except Exception as exc:
                return exc

    probe_tasks = []
    for c in candidates:
        yield {"type": "hype_started", "query": c.query}
        probe_tasks.append(asyncio.create_task(_probe(c.query)))
    for task in asyncio.as_completed(probe_tasks):
        if monotonic() - started > whole_run_timeout_s:
            break
        probe = await task
        if isinstance(probe, Exception):
            hype_errors.append({"message": str(probe)})
            yield {"type": "error", "stage": "hype", "message": str(probe)}
            continue
        hype_results[probe.query] = probe
        yield {"type": "hype_done", **probe.model_dump(mode="json")}
    if not hype_results:
        yield {"type": "error", "stage": "hype", "message": "All hype probes failed"}
        yield {"type": "done", "total_duration_ms": int((monotonic() - started) * 1000), "queries_run": 0, "queries_failed": len(hype_errors), "total_items": 0}
        return

    plan_event: dict | None = None
    try:
        async for event in stream_plan(
            intent_text=intent_text,
            candidates=[c.model_dump(mode="json") for c in candidates],
            hype_results=hype_results,
        ):
            if event["type"] == "plan":
                plan_event = event
            yield event
    except Exception as exc:
        yield {"type": "error", "stage": "plan", "message": str(exc)}
        yield {"type": "done", "total_duration_ms": int((monotonic() - started) * 1000), "queries_run": 0, "queries_failed": 0, "total_items": 0}
        return
    if plan_event is None:
        yield {"type": "error", "stage": "plan", "message": "Planner returned no plan"}
        yield {"type": "done", "total_duration_ms": int((monotonic() - started) * 1000), "queries_run": 0, "queries_failed": 0, "total_items": 0}
        return

    plan = AgentPlan.model_validate({k: v for k, v in plan_event.items() if k != "type"})
    state = AgentRunState(
        seed_params=seed_params,
        intent_reasoning=intent_reasoning,
        candidates=candidates,
        hype_results=hype_results,
        plan=plan,
    )

    search_semaphore = asyncio.Semaphore(4)

    async def _search(query_text: str):
        async with search_semaphore:
            if seed_params is not None:
                base_params = seed_params.model_copy()
            else:
                base_params = SearchParams(live_limit=40, sold_limit=40)
            base_params.query = query_text
            started_q = monotonic()
            try:
                response = await asyncio.wait_for(
                    run_search(base_params, surface_no_data=True),
                    timeout=per_search_timeout_s,
                )
                return {"query": query_text, "duration_ms": int((monotonic() - started_q) * 1000), "items": response.items[:5], "error": None}
            except asyncio.TimeoutError:
                return {"query": query_text, "duration_ms": 0, "items": [], "error": "Search timed out"}
            except Exception as exc:
                return {"query": query_text, "duration_ms": 0, "items": [], "error": str(exc)}

    search_tasks = []
    for picked in plan.picked[:4]:
        yield {"type": "query_started", "query": picked.query, "started_at_unix": int(datetime.now(tz=UTC).timestamp())}
        search_tasks.append(asyncio.create_task(_search(picked.query)))
    for task in asyncio.as_completed(search_tasks):
        if monotonic() - started > whole_run_timeout_s:
            break
        result = await task
        if result["error"] is not None:
            state.query_errors.append({"query": result["query"], "message": result["error"]})
            yield {"type": "error", "stage": "search", "query": result["query"], "message": result["error"]}
            continue
        state.query_items[result["query"]] = result["items"]
        yield {"type": "query_done", "query": result["query"], "duration_ms": result["duration_ms"], "items": [i.model_dump(mode="json") for i in result["items"]]}

    try:
        async for event in stream_summary(state):
            yield event
    except Exception as exc:
        yield {"type": "error", "stage": "summary", "message": str(exc)}
        yield {"type": "summary", "text": "Summary generation unavailable; review ranked items.", "highlights": []}

    total_items = sum(len(v) for v in state.query_items.values())
    yield {
        "type": "done",
        "total_duration_ms": int((monotonic() - started) * 1000),
        "queries_run": len(state.query_items),
        "queries_failed": len(state.query_errors) + len(hype_errors),
        "total_items": total_items,
    }