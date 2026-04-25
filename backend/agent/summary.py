from __future__ import annotations

import json
from collections.abc import AsyncIterator

from backend.agent.llm import extract_json, stream_text
from shared.models import AgentRunState, AgentSummary, SummaryHighlight


async def stream_summary(state: AgentRunState) -> AsyncIterator[dict]:
    items = []
    for query, recs in state.query_items.items():
        for rec in recs[:5]:
            items.append(
                {
                    "query": query,
                    "item_id": rec.item_id,
                    "edge_usd": rec.edge_usd,
                    "p_sell": rec.p_sell,
                    "title": rec.live_listing.name,
                    "designer": rec.live_listing.designer,
                }
            )
    system = (
        "Write concise resale summary. Return strict JSON only at end: "
        '{"text":"...", "highlights":[{"item_id":"...","why":"..."}]}. '
        "Use 1-3 highlights."
    )
    user = json.dumps(
        {
            "plan": state.plan.model_dump(mode="json"),
            "items": items,
            "query_errors": state.query_errors,
        }
    )
    full_text = ""
    async for delta in stream_text(system=system, user=user):
        full_text += delta
        yield {"type": "summary_thinking", "delta": delta}

    payload = extract_json(full_text)
    highlights = [
        SummaryHighlight(
            item_id=str(h.get("item_id", "")).strip(),
            why=str(h.get("why", "")).strip() or "best risk-adjusted candidate",
        )
        for h in payload.get("highlights", [])
        if isinstance(h, dict) and str(h.get("item_id", "")).strip()
    ][:3]
    summary = AgentSummary(
        text=str(payload.get("text", "No summary generated.")),
        highlights=highlights,
    )
    yield {"type": "summary", **summary.model_dump(mode="json")}
