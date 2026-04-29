# groogled

Grailed arbitrage backend — staged search pipeline, structured logs, browser-based X scraper.

## Packages

| Directory  | Purpose |
|------------|---------|
| `backend/` | FastAPI app — search pipeline, recommendations API |
| `scraper/` | Grailed HTTP scraper (Algolia + listings) |
| `xscraper/` | X (Twitter) scraper via Patchright browser automation |
| `ev/`      | Expected-value and sell-probability models |
| `shared/`  | Shared models and Supabase store |

## Setup

Requires [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env          # fill in secrets
```

Apply DB migrations before first run:

```bash
# supabase/migrations/ — run against your project
```

## Running

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

Optional human-readable logs:

```bash
LOG_FORMAT=text uv run uvicorn backend.main:app --reload --port 8000
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `API_KEY` | ✓ | Auth token for all non-health routes |
| `SUPABASE_URL` | ✓ | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✓ | Supabase service role key |
| `ALGOLIA_API_KEY` | ✓ | Algolia search API key |

## API

All routes except `/health` require `Authorization: Bearer $API_KEY`.

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/search` | Run search pipeline |
| `GET` | `/recommendations?limit=50` | Fetch stored recommendations |

## CLI

```bash
uv run python -m backend.cli search "<query>" <live_limit> <sold_limit> [--no-persist] [--json] [--no-color]
```

Examples (run from repo root):

```bash
uv run python -m backend.cli search "margiela gats" 40 40
uv run python -m backend.cli search guidi 20 30 --no-persist
uv run python -m backend.cli search "carol christian poell" 10 10 --json
```

## Tests

```bash
uv run pytest
```

## Recommendation fields

| Field | Description |
|-------|-------------|
| `expected_profit_grailed` | Expected profit selling on Grailed |
| `expected_profit_off_grailed` | Expected profit selling elsewhere |
| `buy_cost` | Recommended buy price |
| `p_sell` | Probability of sale |
| `q50` | Median comparable sale price |
| `confidence_pct` | Model confidence |
| `valuation` | Estimated fair value |
| `sell_probability` | Raw sell probability |
| `live_listing` | Current live listing data |
