# code-brown — backend handoff

Grailed arbitrage finder. This README is the handoff doc for the rest of the team to run the backend locally and call its endpoints. The orchestration internals are still moving — **treat the HTTP endpoints as the contract, not the Python modules.**

For project context, see [docs/SPEC.md](docs/SPEC.md) and [docs/2026-04-25-rest-api-and-ev-persistence-design.md](docs/2026-04-25-rest-api-and-ev-persistence-design.md).

---

## 1. Quick start

Requires Python 3.10+ (we use PEP 604 `str | None` syntax).

```bash
# from repo root
python -m venv .venv
source .venv/bin/activate          # zsh/bash; on fish: source .venv/bin/activate.fish
pip install -r backend/requirements.txt

cp .env.example .env               # then fill it in — see §2
uvicorn backend.main:app --reload --port 8000
```

The server boots if `API_KEY`, `SUPABASE_URL`, and `SUPABASE_SERVICE_ROLE_KEY` are all set and non-empty. Missing any of them and `lifespan` raises on startup — this is intentional.

Sanity check:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

OpenAPI docs auto-generate at `http://localhost:8000/docs` once the server is up.

---

## 2. Environment variables

Each dev runs their own backend on `localhost` with their own keys. **Do not commit `.env`** — it's gitignored.

| Variable | Required | What it is |
|---|---|---|
| `API_KEY` | yes | Bearer token clients must send. Pick anything random, e.g. `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `SUPABASE_URL` | yes | Your Supabase project URL (e.g. `https://xxxx.supabase.co`). Use your own dev project. |
| `SUPABASE_SERVICE_ROLE_KEY` | yes | Service role key from the same project. Keep it server-side only. |
| `ALGOLIA_API_KEY` | yes | Grailed's public Algolia search key. Grab from a Grailed page (Network tab on a search request). |
| `HYPE_TRENDS_TIMEFRAME` | no | Defaults to `today 3-m`. Google Trends timeframe string. |
| `HYPE_TRENDS_GEO` | no | Defaults to empty (worldwide). ISO country code if you want regional data. |

Your Supabase project needs the migrations in `supabase/migrations/` applied — `listings` and `recommendations` tables plus the `list_latest_recommendations` RPC. Run them via the Supabase SQL editor or `supabase db push` if you have the CLI wired.

---

## 3. API reference

All endpoints except `/health` require `Authorization: Bearer $API_KEY`. Missing or wrong token → `401 Unauthorized`.

Request and response bodies are Pydantic models in [shared/models.py](shared/models.py) — that file is the source of truth for shapes. Don't hand-copy them; import or regenerate types from the OpenAPI schema at `/docs`.

### `GET /health`

Public. Returns `{"status":"ok"}`. Use for uptime checks.

### `POST /search`

Scrape Grailed for active listings matching the filters, value each one against sold comparables, rank by `p_sell * edge_usd`, persist, and return the ranked list.

**Request body** — `SearchParams` ([shared/models.py:6](shared/models.py:6)). Only `query` is meaningful as a default; everything else is optional with sensible defaults.

```json
{
  "query": "guidi",
  "department": "menswear",
  "category": "footwear",
  "condition": "is_gently_used",
  "min_price_usd": 0,
  "max_price_usd": 1000000,
  "live_limit": 5,
  "sold_limit": 3,
  "include_sold": true
}
```

**Response** — `SearchResponse` with `metadata` and `items: list[Recommendation]`.

```bash
curl -X POST http://localhost:8000/search \
  -H "Authorization: Bearer $API_KEY" \
  -H "content-type: application/json" \
  -d '{"query":"guidi","live_limit":3,"sold_limit":5}'
```

Expect 5–30s latency: it's hitting Grailed live and pulling sold comps per listing.

### `GET /hype/{term}`

Google Trends-native hype score for a term. URL-encode the term (`comme%20des%20gar%C3%A7ons`).

**Response** — `HypeResult` with `score`, `confidence`, three `TrendSeries` (7d/30d/90d), and `evidence.related`.

```bash
curl "http://localhost:8000/hype/guidi" \
  -H "Authorization: Bearer $API_KEY"
```

Expect 3–15s latency.

### `GET /recommendations`

Latest persisted recommendation per `item_id`, sorted by `edge_usd` desc. This is the cheap read path — no scraping, no Trends calls. Useful for warming up a UI without waiting on `/search`.

**Query params:** `limit` (1–200, default 50).

**Response** — `{"items": [Recommendation, ...]}`. Same `Recommendation` shape as inside `SearchResponse.items`.

```bash
curl "http://localhost:8000/recommendations?limit=20" \
  -H "Authorization: Bearer $API_KEY"
```

Returns `{"items": []}` if no `/search` calls have populated the store yet.

---

## 4. The `Recommendation` shape (what you'll render)

One ranked listing. Returned by both `/search` (inside `items`) and `/recommendations`. Single shape so the frontend writes one renderer.

Top-level typed fields you can sort/filter/display directly:

- `item_id`, `query`, `scraped_at_unix`
- `edge_usd` — expected dollar profit
- `p_sell` — probability the item sells
- `q50` — median expected sale price
- `cost` — total acquisition cost (price + shipping + fees)
- `confidence` — `"high" | "medium" | "low" | "insufficient"`
- `live_listing` — full `LiveListing` (title, designer, size, condition, image URLs, seller, price, etc.)

Two opaque dicts whose internals will grow over time:

- `valuation` — EV math output. Has `dist.q10/q50/q90`, `metrics.edge_usd`, `metrics.percent_under`, `metrics.confidence`, `metrics.effective_n`, `cost`, etc.
- `sell_probability` — sell-time math. Has `p_sell`, `median_days_to_sell`, `adjusted_days_to_sell`, `pricing_ratio`, `q50_comp_price`, `num_valid_time_comps`, `num_sold_comps`, etc.

**Render rule:** read what you know about; ignore unknown keys. The math owner adds fields; nothing is renamed or removed.

---

## 5. What's stable, what's not

Stable — depend on these:
- The four endpoints, their auth model, request and response shapes.
- Top-level typed fields on `Recommendation`.
- Existing keys inside `valuation` / `sell_probability` (additive-only — see [docs/2026-04-25-rest-api-and-ev-persistence-design.md §4.3](docs/2026-04-25-rest-api-and-ev-persistence-design.md)).

Not stable — **don't build against and don't modify**:
- `backend/orchestrator.py` — wiring is being reworked.
- `scraper/`, `ev/`, `hype/`, `shared/store.py` — internal modules. Going through more changes.
- The Supabase schema beyond what's in `supabase/migrations/`.

If you need a new endpoint, a new field, or a behavior change: ping Oliver. Don't add it inline.

---

## 6. Troubleshooting

**`RuntimeError: API_KEY environment variable must be set`** on startup → your `.env` isn't loaded or the value is empty. Confirm you're running from the repo root and `.env` lives there.

**`401 Unauthorized`** on every request → missing `Authorization: Bearer ...` header, or the token doesn't match `API_KEY` in `.env`.

**Supabase errors on `/search` or `/recommendations`** → migrations haven't been applied to your project, or `SUPABASE_SERVICE_ROLE_KEY` is the anon key by mistake. The service role key is the longer one in the project's API settings.

**Port already in use** → `--port 8001` or `lsof -ti:8000 | xargs kill`.

**`/search` is slow / hangs** → it's doing real network calls (Grailed + Algolia). 5–30s is normal. If it's >60s, Grailed may be rate-limiting your IP.

---

## 7. Optional: CLI harness

For poking the orchestrator without the HTTP layer:

```bash
python -m backend.cli search             # interactive prompt
python -m backend.cli search --no-persist  # skip writing to Supabase
python -m backend.cli hype guidi
```

This bypasses `/search` and `/hype` and calls the orchestrator directly. Useful for debugging; not what the frontend should use.
