from __future__ import annotations

import json

from backend.agent.llm import complete_json
from shared.models import CandidateQuery


async def expand_intent_candidates(intent_text: str, *, n: int = 6) -> tuple[str, list[CandidateQuery]]:
    system = (
        "You convert a reseller vibe into concrete Grailed searches. "
        "Return strict JSON only: "
        '{"reasoning":"...", "candidates":[{"query":"...", "why":"..."}]}. '
        f"Generate exactly {n} candidates."
    )
    user = json.dumps({"intent_text": intent_text, "count": n})
    payload = await complete_json(system=system, user=user)
    reasoning = str(payload.get("reasoning", "")).strip()
    raw_candidates = payload.get("candidates", [])
    if not isinstance(raw_candidates, list):
        raise ValueError("Intent output missing candidates list")
    candidates: list[CandidateQuery] = []
    for row in raw_candidates[:n]:
        if not isinstance(row, dict):
            continue
        query = str(row.get("query", "")).strip()
        why = str(row.get("why", "")).strip()
        if query:
            candidates.append(CandidateQuery(query=query, why=why or "high-signal candidate"))
    if len(candidates) < 1:
        raise ValueError("Intent output returned no usable candidates")
    return reasoning or "Intent expanded into demand-neighborhood queries.", candidates[:n]
