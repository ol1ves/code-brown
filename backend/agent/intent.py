from __future__ import annotations

import json

from backend.agent.llm import complete_json
from shared.models import CandidateQuery


async def expand_intent_candidates(intent_text: str, *, n: int = 6) -> tuple[str, list[CandidateQuery]]:
    system = (
        "You convert a reseller vibe into concrete Grailed searches that ALSO yield "
        "interpretable Google Trends signals.\n"
        "\n"
        "Each candidate query is a single search string that will be sent to BOTH "
        "Grailed listings and Google Trends. Long-tail single-designer variants "
        "(e.g. 'margiela tabi', 'margiela replica', 'margiela boots') return "
        "near-zero or identical Google Trends curves, which makes the graphs "
        "indistinguishable. Avoid that.\n"
        "\n"
        "Hard rules:\n"
        f"1. Generate exactly {n} candidates.\n"
        "2. Spread across distinct demand neighborhoods — DO NOT repeat the same "
        "brand more than twice across the candidate set.\n"
        "3. Each candidate should hit a different axis of variation: brand, "
        "garment category (jacket / pant / footwear / knit / accessory), era "
        "(2000s / 90s / archive), or aesthetic (gorpcore, archive, mall goth, "
        "y2k, workwear, etc.).\n"
        "4. Prefer queries with established Google Trends volume — designer name, "
        "category, or aesthetic alone — over rare model names that flatline. "
        "When in doubt, broaden one token (e.g. 'guidi boots' over "
        "'guidi 992 horse leather').\n"
        "5. The 'why' field justifies how this candidate diverges from the "
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
