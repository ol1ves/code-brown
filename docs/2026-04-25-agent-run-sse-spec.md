# Agent Run SSE Spec

Status: approved implementation contract for `/agent/run` and isolated `agent-ui/`.

## Request

`POST /agent/run`

Headers:
- `Authorization: Bearer $API_KEY`
- `Content-Type: application/json`

Body:

```json
{ "intent_text": "find me underpriced archive 2000s pieces" }
```

Optional backend-dev escape hatch:

```json
{
  "intent_text": "ignored when seed_params present",
  "seed_params": {
    "query": "carol christian poell",
    "department": "menswear",
    "category": "footwear"
  }
}
```

## Stream Format

- Response content type: `text/event-stream`
- Each event is exactly `data: <json>\n\n`
- Event order contract (happy path):
  1) `intent_parsed`
  2) `candidates_generated`
  3) `hype_started` x N (N=6 default)
  4) `hype_done` x N (interleaved)
  5) `plan_thinking` x N
  6) `plan`
  7) `query_started` x <=4 (interleaved)
  8) `query_done` x <=4 (interleaved)
  9) `summary_thinking` x N
  10) `summary`
  11) `done` terminal

## Event Types

### `intent_parsed`

```json
{
  "type": "intent_parsed",
  "reasoning": "Mapped archive 2000s vibe to candidates with strong resale demand",
  "candidates": [
    { "query": "carol christian poell", "why": "high-signal archive menswear brand" },
    { "query": "ccp boots", "why": "strong niche demand and pricing dispersion" }
  ]
}
```

### `candidates_generated`

```json
{
  "type": "candidates_generated",
  "candidates": [
    { "query": "carol christian poell", "why": "high-signal archive menswear brand" }
  ]
}
```

### `hype_started`

```json
{ "type": "hype_started", "query": "ccp boots" }
```

### `hype_done`

```json
{
  "type": "hype_done",
  "query": "ccp boots",
  "score": 47,
  "confidence": "high",
  "momentum_pct": 38,
  "related": [{ "query": "horsehide derby", "value": 28, "kind": "rising", "is_breakout": false }]
}
```

### `plan_thinking`

```json
{ "type": "plan_thinking", "delta": "Selecting high-signal related queries..." }
```

### `plan`

```json
{
  "type": "plan",
  "seed": "archive 2000s vibe",
  "hype": { "score": 47, "confidence": "high", "momentum_7d_vs_90d_pct": 38 },
  "picked": [
    { "query": "ccp boots", "momentum_pct": 42, "reasoning": "7d up 42%" }
  ],
  "skipped": [
    { "query": "ccp sneakers", "reason": "lower momentum" }
  ]
}
```

### `query_started`

```json
{ "type": "query_started", "query": "ccp boots", "started_at_unix": 1745567890 }
```

### `query_done`

```json
{
  "type": "query_done",
  "query": "ccp boots",
  "duration_ms": 8420,
  "items": []
}
```

### `summary_thinking`

```json
{ "type": "summary_thinking", "delta": "Combining strongest opportunities..." }
```

### `summary`

```json
{
  "type": "summary",
  "text": "I explored 4 related markets and found 3 strong opportunities.",
  "highlights": [{ "item_id": "abc", "why": "edge $240, p_sell .68" }]
}
```

### `done` (terminal)

```json
{
  "type": "done",
  "total_duration_ms": 14820,
  "queries_run": 4,
  "queries_failed": 0,
  "total_items": 12
}
```

### `error`

```json
{ "type": "error", "stage": "search", "query": "ccp boots", "message": "Algolia 429" }
```

Terminality rule:
- `stage` in `intent|plan`: fatal, stream still ends with `done` for consistency.
- `stage` in `hype|search|summary`: non-terminal, continue run (except all-hype-failed case).

## Backend Invariants

- Fan-out cap: `<=4` picked queries per run.
- Candidate generation cap: `6` default.
- Hype fan-out cap: `<=4` in parallel.
- Per-search timeout: 25s. Timeout emits non-terminal `error`.
- Per-hype timeout: 15s. Timeout emits non-terminal `error(stage=hype)`.
- Whole-run timeout: 60s. Emit `done` with completed partials.
- Stateless run: no `run_id`, no resume, no server memory across requests.

## Frontend Merge/Dedup Rule

When receiving `query_done.items`:
- key by `live_listing.id`
- if duplicate appears across queries, keep entry with greater `p_sell * edge_usd`
- track query hit count per listing for badge: `found across N queries`
- sort global ranked list descending by `p_sell * edge_usd`

## Isolated Frontend Rule

- New UI must live under top-level `agent-ui/`
- No edits, imports, or coupling with existing `frontend/` directory

## Acceptance Matrix

| Layer | Scenario | Expected |
|---|---|---|
| Backend stream | happy path | ordered event families ending with `done` |
| Backend stream | hype visibility | emits `candidates_generated`, `hype_started`, `hype_done` with interleaved completion |
| Backend stream | intent/planner failure | `error(stage=intent|plan)` then `done` |
| Backend stream | partial hype failures | non-terminal `error(stage=hype, query=...)`, planner runs with successful probes |
| Backend stream | per-search timeout | non-terminal `error(stage=search, query=...)`, other queries continue |
| Backend stream | whole-run timeout | partial query outputs allowed, always final `done` |
| Frontend parser | split chunk boundaries | no dropped/merged malformed events |
| Frontend reducer | duplicate listing across queries | keep higher `p_sell*edge_usd`, increment `foundAcrossQueries` |
| Frontend UI | interleaved query completion order | pills + ranked list update correctly without assuming order |
