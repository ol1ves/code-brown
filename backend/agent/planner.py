from __future__ import annotations

import json
from collections.abc import AsyncIterator

from backend.agent.llm import extract_json, stream_text
from shared.models import HypeProbeResult, PlanPickedQuery, PlanSkippedQuery


async def stream_plan(
    *,
    intent_text: str,
    candidates: list[dict],
    hype_results: dict[str, HypeProbeResult],
) -> AsyncIterator[dict]:
    system = (
        "Rank candidate search queries using hype evidence. "
        "Return strict JSON only at end with this schema: "
        '{"seed":"...", "hype":{"score":0,"confidence":"medium","momentum_7d_vs_90d_pct":0},'
        '"picked":[{"query":"...","momentum_pct":0,"reasoning":"..."}],'
        '"skipped":[{"query":"...","reason":"..."}]}. '
        "Pick at most 4."
    )
    user = json.dumps(
        {
            "intent_text": intent_text,
            "candidates": candidates,
            "hype_results": {k: v.model_dump(mode="json") for k, v in hype_results.items()},
        }
    )
    full_text = ""
    async for delta in stream_text(system=system, user=user):
        full_text += delta
        yield {"type": "plan_thinking", "delta": delta}

    payload = extract_json(full_text)
    picked_raw = payload.get("picked", [])
    skipped_raw = payload.get("skipped", [])
    picked = [
        PlanPickedQuery(
            query=str(row.get("query", "")).strip(),
            momentum_pct=int(row.get("momentum_pct", 0)),
            reasoning=str(row.get("reasoning", "")).strip() or "selected by planner",
        )
        for row in picked_raw
        if isinstance(row, dict) and str(row.get("query", "")).strip()
    ][:4]
    skipped = [
        PlanSkippedQuery(
            query=str(row.get("query", "")).strip(),
            reason=str(row.get("reason", "")).strip() or "not selected",
        )
        for row in skipped_raw
        if isinstance(row, dict) and str(row.get("query", "")).strip()
    ]
    if not picked:
        best = sorted(hype_results.values(), key=lambda r: (r.score or 0, r.momentum_pct), reverse=True)[:4]
        picked = [
            PlanPickedQuery(query=r.query, momentum_pct=r.momentum_pct, reasoning="fallback from hype rank")
            for r in best
        ]

    yield {
        "type": "plan",
        "seed": str(payload.get("seed", intent_text)),
        "hype": payload.get("hype", {"score": 0, "confidence": "insufficient", "momentum_7d_vs_90d_pct": 0}),
        "picked": [p.model_dump(mode="json") for p in picked],
        "skipped": [s.model_dump(mode="json") for s in skipped],
    }
