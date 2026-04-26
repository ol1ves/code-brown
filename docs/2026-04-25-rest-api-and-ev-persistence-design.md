## REST API Skeleton + EV Recommendation Persistence — Design Spec

**Status:** partially superseded by [2026-04-26 backend orchestration rewrite](superpowers/specs/2026-04-26-backend-orchestration-rewrite-design.md). Field names (`edge_usd`, `cost`, `confidence`) changed.

**Status:** approved, pending implementation plan
**Owner:** Oliver
**Last updated:** 2026-04-25
**Related:** [SPEC.md](SPEC.md), [docs/2026-04-25-backend-mvp-wiring.md](2026-04-25-backend-mvp-wiring.md), [ev/EV_MODEL_SPEC.md](../ev/EV_MODEL_SPEC.md), [supabase/migrations/20260424194700_init_listings.sql](../supabase/migrations/20260424194700_init_listings.sql)

---

### 1. Summary

Wrap the existing `run_search` / `run_hype` orchestrator in a thin FastAPI surface, persist every ranked listing to a new `recommendations` table (hybrid typed-columns + raw JSONB), and expose a `GET /recommendations` read endpoint so the Next.js frontend can render real data without coupling to scraper internals.

The whole point: **unblock the frontend dev with real data, today, without locking us into a contract that breaks every time the EV math evolves.**

Three load-bearing constraints, all addressable in the schema:

1. **EV math is moving.** The math owner will add fields to `valuation` and `sell_probability` outputs. We commit to additive-only changes; nothing in either dict is renamed or removed.
2. **Frontend must not be re-deployed every time math adds a field.** New EV fields land in JSONB blobs that pass through the API verbatim.
3. **Future agent tooling needs to query across recommendations.** The handful of fields we actually rank/filter on get promoted to typed columns now.

---

### 2. Scope

**In scope:**
- New Supabase migration creating `public.recommendations`.
- New method on `shared/store.py:ListingStore` to bulk-insert ranked rows.
- Synchronous persist call inside `backend/orchestrator.py:run_search`, after the response is built and before it's returned.
- Three new FastAPI handlers in `backend/main.py`: `POST /search`, `GET /hype/{term}`, `GET /recommendations`.
- A small `RecommendationListItem` pydantic model for the read endpoint.
- Documentation snippet showing the Next.js route-handler proxy pattern (the frontend dev will write the actual proxies; we just lock the contract).
- Unit + smoke tests covering the new persistence path and handlers.

**Out of scope:**
- The Next.js proxy implementation itself. Backend ships the contract; frontend ships the proxy.
- Any new EV fields. The math owner adds those independently — the design here works for whatever the dicts contain today and tomorrow.
- Pagination cursors, filtering by designer, agent tooling, "search by hype". All deferred (see §11).
- A `search_runs` parent table. Explicitly ruled out — standalone rows.
- Authentication beyond the existing bearer token.
- CORS configuration on FastAPI. The proxy pattern means the browser never talks to FastAPI directly.
- Any change to the existing `listings` table or the scraper's writes to it. That cache continues exactly as-is.

---

### 3. Architecture

```
Browser
  │ fetch /api/search          (same-origin)
  ▼
Next.js route handler          (server-side, holds API_KEY)
  │ POST /search  Bearer …     (cross-origin, server→server)
  ▼
FastAPI handler                (backend/main.py)
  │ await orchestrator.run_search(params)
  ▼
backend/orchestrator.run_search
  │ scraper.scrape(persist=True)        →  writes raw listings to public.listings
  │ value_listing + estimate_sell_probability per row
  │ rank by p_sell * edge_usd
  │ store.save_recommendations(response, params)   ← NEW; sync; in-request
  ▼
SearchResponse  →  FastAPI  →  Next.js handler  →  Browser
```

Read path:

```
Browser → /api/recommendations → Next.js handler → GET /recommendations → FastAPI
                                                       │
                                                       ▼
                                          ListingStore.list_recommendations()
                                                       │
                                          distinct on (item_id) order by
                                          item_id, scraped_at_unix desc
                                                       │
                                                       ▼
                                          [RecommendationListItem, …]
```

No new modules. No new background workers. No queue. The persistence call sits inline in `run_search` immediately before `return SearchResponse(...)`.

---

### 4. Data — `public.recommendations`

#### 4.1 Migration DDL

New file: `supabase/migrations/20260425000000_init_recommendations.sql`.

```sql
create table public.recommendations (
  id              uuid primary key default gen_random_uuid(),
  item_id         text not null,
  scraped_at_unix bigint not null,
  query           text not null,
  params          jsonb not null,
  edge_usd        numeric not null,
  p_sell          numeric not null,
  q50             numeric not null,
  cost            numeric not null,
  confidence      text not null,
  valuation       jsonb not null,
  sell_probability jsonb not null,
  live_listing    jsonb not null,
  created_at      timestamptz not null default now()
);

create index recommendations_item_id_scraped_at_idx
  on public.recommendations (item_id, scraped_at_unix desc);
create index recommendations_edge_usd_idx
  on public.recommendations (edge_usd desc);
create index recommendations_created_at_idx
  on public.recommendations (created_at desc);

alter table public.recommendations disable row level security;
```

#### 4.2 Column rationale

The hybrid choice (Option A from brainstorming) lives or dies on which fields are promoted. Rule: **a field becomes a column only if a query needs to sort or filter on it cheaply.**

| Column            | Why typed (not JSONB-only) |
|-------------------|----------------------------|
| `item_id`         | Dedupe key for "latest per item". |
| `scraped_at_unix` | Tie-break for "latest per item"; matches the EV input contract (see [EV_MODEL_SPEC §2](../ev/EV_MODEL_SPEC.md)). |
| `query`           | Likely first filter the frontend or any agent ever wants. |
| `edge_usd`        | Default sort. Index it. |
| `p_sell`          | The other half of the ranking score; agent tooling will filter on it. |
| `q50`, `cost`     | Frontend will display these directly; cheap to extract. |
| `confidence`      | Filter ("high confidence only") — small cardinality, useful in UI. |

Everything else stays in `valuation jsonb` / `sell_probability jsonb` / `live_listing jsonb`. New EV fields land in those blobs with no schema change.

#### 4.3 Additive-only rule (operational)

The math owner is free to add keys to either `valuation` or `sell_probability` at any time. The persist code reads the dicts as opaque JSON. The API returns them as opaque JSON. The frontend renders whatever it knows about and ignores the rest.

If a new field eventually deserves promotion to a typed column (frontend wants to sort on it, agent wants to filter on it), the migration is a one-shot:

```sql
alter table public.recommendations add column foo numeric;
update public.recommendations set foo = (valuation->>'foo')::numeric where foo is null;
-- backfill is best-effort; missing on old rows is acceptable
```

**Hard rule:** no field is ever removed from `valuation` or `sell_probability`. No field is ever renamed. Renames = a new key alongside the old one + a deprecation note in `EV_MODEL_SPEC.md`. This is the contract that lets the frontend and the math guy ship in parallel.

#### 4.4 Why no `run_id`

Resolved in brainstorming: standalone rows, no parent. If we later want to group, we have `created_at` and `scraped_at_unix` and the full `params` blob — enough to reconstruct any single search after the fact.

---

### 5. `shared/store.py:ListingStore` — additions

Add two methods. No existing methods change.

```python
def save_recommendations(
    self,
    *,
    response: "SearchResponse",
    params: "SearchParams",
) -> None:
    """Bulk-insert one row per ranked listing. No-op if response.ranked is empty."""
    if not response.ranked:
        return
    scraped_at = response.metadata.scraped_at_unix
    query = params.query
    params_json = params.model_dump(mode="json")
    rows = []
    for item in response.ranked:
        metrics = item.valuation["metrics"]
        rows.append({
            "item_id": item.live_listing.id,
            "scraped_at_unix": scraped_at,
            "query": query,
            "params": params_json,
            "edge_usd": metrics["edge_usd"],
            "p_sell": item.sell_probability["p_sell"],
            "q50": item.valuation["dist"]["q50"],
            "cost": item.valuation["cost"],
            "confidence": metrics["confidence"],
            "valuation": item.valuation,
            "sell_probability": item.sell_probability,
            "live_listing": item.live_listing.model_dump(mode="json"),
        })
    self._db.table("recommendations").insert(rows).execute()


def list_recommendations(self, *, limit: int = 50) -> list[dict]:
    """Latest row per item_id, ordered by edge_usd desc.

    Implementation detail: PostgREST does not expose ``DISTINCT ON``,
    so we run a SQL RPC. See migration §6 below for the function.
    """
    res = self._db.rpc(
        "list_latest_recommendations",
        {"p_limit": limit},
    ).execute()
    return res.data or []
```

The `list_recommendations` call is deliberately a stored function (Supabase RPC) instead of a chained `select` because PostgREST cannot express `distinct on`. The function is created in the same migration as the table:

```sql
create or replace function public.list_latest_recommendations(p_limit int)
returns setof public.recommendations
language sql stable as $$
  with latest as (
    select distinct on (item_id) *
    from public.recommendations
    order by item_id, scraped_at_unix desc, edge_usd desc
  )
  select * from latest
  order by edge_usd desc
  limit p_limit;
$$;
```

Two-stage: the `distinct on` collapses to one row per `item_id` (newest scrape wins; `edge_usd desc` tie-breaks two writes in the same scrape moment). Then the outer `order by edge_usd desc + limit` picks the global top N. Without the CTE, `limit` would slice the alphabetical-by-`item_id` list before ranking, returning the wrong 50 items.

The handler re-sorts in Python (§7.3) as belt-and-suspenders — the RPC ordering is part of the contract but the in-memory sort guarantees it regardless of any future RPC change.

---

### 6. `backend/orchestrator.py` — single-line change

`run_search` already takes `persist: bool = True`. After ranking and before returning, if `persist=True`, call `store.save_recommendations(...)`.

The store is wired by `backend/main.py:lifespan` (already done) and by `backend/cli.py:_wire_stores` (already done). The orchestrator imports the store via a module-level accessor — same pattern as `scraper.scraper:set_store` — so the orchestrator does not import Supabase directly.

```python
# new in shared/store.py: a tiny module-level accessor
_recommendations_store: ListingStore | None = None

def set_recommendations_store(store: ListingStore) -> None:
    global _recommendations_store
    _recommendations_store = store

def get_recommendations_store() -> ListingStore | None:
    return _recommendations_store
```

`backend/main.py:lifespan` and `backend/cli.py:_wire_stores` both call `set_recommendations_store(store)` alongside the existing `set_scraper_store` / `set_ev_store` calls.

`run_search`:

```python
async def run_search(params: SearchParams, *, persist: bool = True) -> SearchResponse:
    scrape_result = await scrape(params, persist=persist)
    # ... existing valuation + ranking loop unchanged ...
    response = SearchResponse(metadata=scrape_result.metadata, ranked=ranked)
    if persist:
        store = get_recommendations_store()
        if store is not None:
            store.save_recommendations(response=response, params=params)
    return response
```

**Failure semantics (locked):** the persist call runs synchronously inside the request. If the Supabase write raises, the exception propagates to the FastAPI handler and the request returns 500. The user gets an honest failure; no silent data loss. This was Option A in brainstorming.

**Why guard on `store is not None`:** lets `--no-persist` CLI runs and unit tests skip persistence without monkey-patching. If `persist=True` but no store is wired, that's a misconfiguration in dev — we no-op rather than crash, but log nothing fancy. The integration check in §10 catches this.

---

### 7. `backend/main.py` — three new handlers

#### 7.1 `POST /search`

```python
from backend.orchestrator import run_search
from shared.models import SearchParams, SearchResponse

@app.post("/search", response_model=SearchResponse)
async def search(params: SearchParams) -> SearchResponse:
    return await run_search(params)
```

That's it. Bearer auth from the existing middleware applies. `persist=True` is the default. `SearchParams` and `SearchResponse` are already pydantic models; FastAPI handles validation, OpenAPI schema, and JSON serialization.

#### 7.2 `GET /hype/{term}`

```python
from backend.orchestrator import run_hype
from shared.models import HypeResult

@app.get("/hype/{term}", response_model=HypeResult)
async def hype(term: str) -> HypeResult:
    return await run_hype(term)
```

`term` is path-encoded; the frontend URL-encodes it. Spaces and slashes in designer names work fine after encoding (e.g. `comme%20des%20gar%C3%A7ons`).

#### 7.3 `GET /recommendations`

```python
from typing import Literal
from fastapi import Query
from pydantic import BaseModel, Field
from shared.models import LiveListing
from shared.store import get_recommendations_store

class RecommendationListItem(BaseModel):
    item_id: str
    scraped_at_unix: int
    query: str
    edge_usd: float
    p_sell: float
    q50: float
    cost: float
    confidence: str
    valuation: dict
    sell_probability: dict
    live_listing: LiveListing

class RecommendationsResponse(BaseModel):
    items: list[RecommendationListItem] = Field(default_factory=list)

@app.get("/recommendations", response_model=RecommendationsResponse)
def recommendations(
    limit: int = Query(default=50, ge=1, le=200),
) -> RecommendationsResponse:
    store = get_recommendations_store()
    if store is None:
        return RecommendationsResponse(items=[])
    rows = store.list_recommendations(limit=limit)
    items = [RecommendationListItem.model_validate(r) for r in rows]
    items.sort(key=lambda r: r.edge_usd, reverse=True)
    return RecommendationsResponse(items=items)
```

Sorting is done in Python after fetch because the RPC's `distinct on` requires `order by item_id` first. The result set is bounded (`limit ≤ 200`), so the in-memory sort is free.

The `sort` query param is **not** implemented yet. The handler signature ships with `limit` only. Future sort options live in §11.

---

### 8. Auth + Next.js proxy pattern

No backend change. Documenting the contract so the frontend dev can wire it without ambiguity.

**Frontend (Next.js App Router) — server-side route handler:**

```ts
// frontend/src/app/api/search/route.ts
export async function POST(req: Request) {
  const body = await req.text();
  const upstream = await fetch(`${process.env.BACKEND_URL}/search`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${process.env.BACKEND_API_KEY}`,
    },
    body,
  });
  return new Response(upstream.body, {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
```

`BACKEND_URL` and `BACKEND_API_KEY` live in `frontend/.env.local`, never prefixed `NEXT_PUBLIC_`. The browser only ever talks to the Next origin (`/api/search`, `/api/hype/...`, `/api/recommendations`). No CORS config needed on FastAPI. The API key is never in the JS bundle.

Three proxy routes total: `/api/search`, `/api/hype/[term]`, `/api/recommendations`. Each is ~15 lines. The frontend dev owns these files; the backend owns only the FastAPI side.

---

### 9. Testing

#### 9.1 Unit tests

`tests/test_store_recommendations.py` (new):

- `test_save_recommendations_inserts_one_row_per_ranked_item` — mock the supabase `Client`, build a `SearchResponse` with 3 ranked items, assert `insert` was called with a 3-element list and the right column shapes.
- `test_save_recommendations_noop_on_empty_ranked` — empty `ranked` → no insert call.
- `test_save_recommendations_extracts_typed_columns_correctly` — verify `edge_usd`, `p_sell`, `q50`, `cost`, `confidence` come out of the right dict paths.
- `test_save_recommendations_passes_params_as_jsonb` — the `params` column equals `params.model_dump(mode="json")`.

`tests/test_orchestrator.py` (extend):

- `test_run_search_persists_when_store_set` — wire a fake store via `set_recommendations_store`, run `run_search`, assert `save_recommendations` called once.
- `test_run_search_skips_persist_when_persist_false` — assert no call.
- `test_run_search_skips_persist_when_no_store_wired` — `persist=True` but `set_recommendations_store(None)` → no crash, no call.

#### 9.2 API smoke tests

`tests/test_api_smoke.py` (new) — uses `fastapi.testclient.TestClient`:

- `test_search_handler_invokes_orchestrator` — patch `orchestrator.run_search`, POST a `SearchParams` body, assert response shape and that the orchestrator was awaited with the parsed params.
- `test_hype_handler_invokes_orchestrator` — patch `orchestrator.run_hype`, GET `/hype/guidi`.
- `test_recommendations_handler_returns_items` — patch the store's `list_recommendations` to return two fake rows, GET `/recommendations`, assert response items sorted by `edge_usd` desc.
- `test_recommendations_handler_respects_limit_bounds` — `?limit=0` and `?limit=999` both 422.
- `test_search_requires_bearer` — no `Authorization` header → 401.
- `test_health_does_not_require_bearer` — sanity check, existing behavior.

#### 9.3 Pytest config

Already covers `tests/`. No change.

---

### 10. Manual integration check (run before claiming done)

1. Apply the migration: `supabase db push` (or local equivalent).
2. Start the backend: `uvicorn backend.main:app --reload --port 8000`.
3. `curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/health` → `{"status":"ok"}`.
4. `curl -X POST -H "Authorization: Bearer $API_KEY" -H "content-type: application/json" \
        -d '{"query":"guidi","live_limit":3,"sold_limit":5}' \
        http://localhost:8000/search` → ranked JSON response in 5-30s.
5. Open Supabase Studio → `recommendations` table → confirm N rows for the search just run, with `valuation` and `sell_probability` populated.
6. `curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/recommendations?limit=20` → JSON list, sorted by `edge_usd` desc, deduped per `item_id`.
7. `curl -H "Authorization: Bearer $API_KEY" http://localhost:8000/hype/guidi` → `HypeResult` JSON in 3-15s.
8. Run `/search` for the same query a second time. Confirm `recommendations` row count grew, but `GET /recommendations` did not duplicate `item_id`s (latest-only dedupe working).

If any of 4-8 fails, the bug is in the new wiring, not the underlying modules — the unit tests cover those.

---

### 11. File-level changes

**Create:**
- `supabase/migrations/20260425000000_init_recommendations.sql` — table + indexes + RPC function.
- `tests/test_store_recommendations.py`
- `tests/test_api_smoke.py`

**Modify:**
- `shared/store.py` — add `save_recommendations`, `list_recommendations`, `set_recommendations_store`, `get_recommendations_store`.
- `backend/orchestrator.py` — call `save_recommendations` at end of `run_search` when `persist=True` and a store is wired.
- `backend/main.py` — wire `set_recommendations_store(store)` in `lifespan`; add three handlers + `RecommendationListItem` and `RecommendationsResponse` models.
- `backend/cli.py` — call `set_recommendations_store(store)` in `_wire_stores`.
- `tests/test_orchestrator.py` — add three persist-related cases.

**Do NOT touch:**
- `scraper/`, `hype/`, `ev/` source — no module behavior changes.
- The existing `public.listings` table or its indexes — the scraper cache continues exactly as-is.
- `backend/main.py` bearer middleware or `lifespan` Supabase wiring (other than the one new `set_recommendations_store` call).

---

### 12. Future work (deferred)

- **Pagination cursor** on `/recommendations` — `?after=<created_at>`. Not needed until row count makes `limit=200` feel small.
- **Filter by designer / category / confidence** on `/recommendations`. Trivially added when frontend asks; the typed columns are already there or can be promoted from JSONB.
- **`?sort=` param** — `edge_usd | p_sell | edge_x_psell`. One match-statement in the handler.
- **Promote new EV fields to typed columns** as agent tooling needs them. Each promotion = one `alter table` + best-effort backfill from JSONB.
- **`search_runs` parent table** if a "my past searches" view ever ships. Migration is non-destructive: add table, add nullable `run_id` column, backfill is optional.
- **Search-by-hype** as you mentioned in the framing. Almost certainly its own endpoint that joins `recommendations` against a hype cache; out of scope until both sides exist.
- **Rate limits / per-user keys.** Today's single API key is fine for the frontend dev. Real auth is a separate spec.
- **CORS on FastAPI** if the proxy pattern is ever abandoned. Not planned.

---

### 13. Locked decisions

| Decision | Resolution | From |
|---|---|---|
| Persist EV recommendations to Supabase? | Yes — Option C from brainstorming: per-ranked-item rows with queryable columns. | Q1 |
| Schema style for additive EV fields | Hybrid — stable typed columns + raw `valuation jsonb` / `sell_probability jsonb`. | Q2 |
| Persist timing | Synchronous, in-request, inside `run_search`. Failures propagate. | Q3 |
| Endpoint surface | `POST /search`, `GET /hype/{term}`, `GET /recommendations`, `GET /health`. | Q4 |
| Frontend auth model | Next.js server-side route handlers proxy with bearer; key never in browser. | Q5 |
| Parent table for runs? | No. Standalone rows, no `run_id`. | Q6 |
| `/recommendations` dedupe | Latest-only per `item_id`, sorted by `edge_usd` desc. | Q7 |
| Per-row search context | `query text` + full `params jsonb`. | Q8 |
| EV field evolution rule | Additive-only. No removes, no renames. Promotions to typed columns are one-shot migrations. | §4.3 |

---

### 14. Open items

None. Ready for implementation plan.
