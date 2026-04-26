# code-brown backend

Grailed arbitrage backend with a staged search pipeline and structured logs.

## 1. Quick start

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cp .env.example .env
uvicorn backend.main:app --reload --port 8000
```

Optional human-readable logs:

```bash
LOG_FORMAT=text uvicorn backend.main:app --reload --port 8000
```

## 2. Environment

Required:

- `API_KEY`
- `SUPABASE_URL`
- `SUPABASE_SERVICE_ROLE_KEY`
- `ALGOLIA_API_KEY`

Apply migrations in `supabase/migrations/` before using `/recommendations`.

## 3. API

All routes except `/health` require `Authorization: Bearer $API_KEY`.

- `GET /health`
- `POST /search`
- `GET /recommendations?limit=50`

Removed routes:

- `GET /hype/{term}`
- `POST /agent/run`

## 4. Recommendation shape

Top-level fields now include:

- `expected_profit_grailed`
- `expected_profit_off_grailed`
- `buy_cost`
- `p_sell`
- `q50`
- `confidence_pct`
- `valuation`
- `sell_probability`
- `live_listing`

Removed from top-level:

- `edge_usd`
- `cost`
- `confidence`

## 5. CLI

```bash
python -m backend.cli search "<query>" <live_limit> <sold_limit> [--no-persist] [--json] [--no-color]
```

Examples:

```bash
python -m backend.cli search "margiela gats" 40 40
python -m backend.cli search guidi 20 30 --no-persist
python -m backend.cli search "carol christian poell" 10 10 --json
```