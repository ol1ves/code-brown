from __future__ import annotations

import json

from backend.agent.llm import complete_json
from shared.models import CandidateQuery


async def expand_intent_candidates(intent_text: str, *, n: int = 6) -> tuple[str, list[CandidateQuery]]:
    system = (
        "You convert a reseller vibe into concrete Grailed searches that ALSO yield "
        "interpretable Google Trends signals.\n"
        "\n"
        "Each candidate query is sent VERBATIM to BOTH Grailed listings and Google "
        "Trends. Google Trends has very low signal for queries longer than 3 "
        "tokens or with adjectives like color/size/condition — they all return "
        "empty 'NO TREND DATA' curves, defeating the purpose of the probe.\n"
        "\n"
        "Hard rules:\n"
        f"1. Generate exactly {n} candidates.\n"
        "2. **Each query MUST be 1-3 tokens.** NEVER more than 3. Drop colors, "
        "sizes, conditions, sub-models. Bad: 'maison margiela replica gat white'. "
        "Good: 'margiela gat', 'replica sneaker', 'german army trainer'.\n"
        "3. Do NOT repeat the same brand in more than 2 candidates. If the user "
        "intent is locked to one product, diversify by broadening (designer "
        "alone, the silhouette category, the aesthetic movement).\n"
        "4. Spread axes: brand / garment category (jacket, pant, footwear, knit, "
        "accessory) / era (2000s, 90s, archive) / aesthetic (gorpcore, archive, "
        "mall goth, y2k, workwear).\n"
        "5. Prefer queries with established Trends volume — designer name, "
        "category, or aesthetic — over rare model names that flatline.\n"
        "6. The 'why' field justifies how this candidate diverges from the "
        "others, not just why it matches the vibe.\n"
        "\n"
        "Return strict JSON only: "
        '{"reasoning":"...", "candidates":[{"query":"...", "why":"..."}]}.'
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
