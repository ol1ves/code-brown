from __future__ import annotations

import json

from backend.agent.llm import complete_json
from shared.models import CandidateQuery


async def expand_intent_candidates(intent_text: str, *, n: int = 6) -> tuple[str, list[CandidateQuery]]:
    system = (
        "You convert a reseller vibe into Grailed search candidates. "
        "Each candidate has TWO levels:\n"
        "  - query: a SPECIFIC Grailed search to find listings. "
        "Designer + product type + key attribute. "
        'Examples: "guidi 992 horsehide", "rick owens ramones grey", '
        '"chrome hearts cross t-shirt".\n'
        "  - hype_term: a BROADER Google Trends probe that has real search volume. "
        "1-2 words. Usually the designer alone or a well-known category/style. "
        "Multiple candidates SHOULD share the same hype_term when they belong to the "
        'same demographic. Examples: "guidi", "rick owens", "chrome hearts", '
        '"archive fashion", "y2k denim". '
        "Niche product names return empty Trends data; use the parent brand or "
        "demographic instead.\n"
        "  - why: short reason.\n"
        "Return strict JSON only: "
        '{"reasoning":"...", '
        '"candidates":[{"query":"...","hype_term":"...","why":"..."}]}. '
        f"Generate exactly {n} candidates. Group narrow queries under shared hype_terms "
        "where it makes sense."
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
        hype_term = str(row.get("hype_term", "")).strip()
        if not query:
            continue
        if not hype_term:
            hype_term = query
        candidates.append(
            CandidateQuery(
                query=query,
                why=why or "high-signal candidate",
                hype_term=hype_term,
            )
        )
    if len(candidates) < 1:
        raise ValueError("Intent output returned no usable candidates")
    return reasoning or "Intent expanded into demand-neighborhood queries.", candidates[:n]
