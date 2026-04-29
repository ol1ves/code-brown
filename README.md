# groogled

Grailed arbitrage backend — staged search pipeline, structured logs, browser-based X scraper.

## Packages

| Directory | Purpose |
|-----------|---------|
| `backend/` | FastAPI app — search pipeline, recommendations API |
| `scraper/` | Grailed HTTP scraper (Algolia + listings) |
| `xscraper/` | X (Twitter) scraper via Patchright browser automation |
| `ev/` | Expected-value and sell-probability models |
| `shared/` | Shared models and Supabase store |

---

## Setup

This repo uses [uv](https://docs.astral.sh/uv/) for Python dependency management. Install it first:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Then install deps and configure your environment:

```bash
uv sync                   # install all deps into .venv
cp .env.example .env      # then fill in secrets (see Environment section)
```

> `uv sync` is idempotent — safe to re-run after pulling or switching branches.

Apply DB migrations before first run:

```bash
# Run SQL files in supabase/migrations/ against your Supabase project
```

---

## Running

```bash
uv run uvicorn backend.main:app --reload --port 8000
```

Human-readable logs:

```bash
LOG_FORMAT=text uv run uvicorn backend.main:app --reload --port 8000
```

> Always use `uv run <cmd>` instead of activating the venv manually. It ensures the right Python and deps are used. You can also `source .venv/bin/activate` if you prefer a persistent shell session.

---

## Dependencies

All deps live in [`pyproject.toml`](pyproject.toml). The [`uv.lock`](uv.lock) file pins exact versions and is committed to the repo — do not edit it by hand.

### Adding a dependency

```bash
uv add <package>              # runtime dep
uv add --dev <package>        # dev-only dep (pytest, linters, etc.)
```

This updates `pyproject.toml` and `uv.lock` automatically. Commit both files.

### Removing a dependency

```bash
uv remove <package>
```

### Upgrading dependencies

```bash
uv lock --upgrade             # upgrade all to latest allowed versions
uv lock --upgrade-package <package>   # upgrade one package
uv sync                       # apply the updated lockfile to .venv
```

### Installing without upgrading (CI / fresh clone)

```bash
uv sync --frozen              # install exactly what's in uv.lock, no resolution
```

> **uv docs:** [Managing dependencies](https://docs.astral.sh/uv/concepts/projects/dependencies/) · [Lockfiles](https://docs.astral.sh/uv/concepts/projects/layout/#the-lockfile) · [uv sync](https://docs.astral.sh/uv/reference/cli/#uv-sync)

---

## Environment variables

Copy `.env.example` to `.env` and fill in values. Never commit `.env`.

| Variable | Required | Description |
|----------|----------|-------------|
| `API_KEY` | ✓ | Bearer token for all non-health routes. Generate with `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `SUPABASE_URL` | ✓ | Supabase project URL |
| `SUPABASE_SERVICE_ROLE_KEY` | ✓ | Supabase service role key (long one in API settings) |
| `ALGOLIA_API_KEY` | ✓ | Grailed's public Algolia key — grab from a search request in the Network tab |
| `HYPE_TRENDS_TIMEFRAME` | — | Google Trends window (default: `today 3-m`) |
| `HYPE_TRENDS_GEO` | — | Google Trends geo filter (default: global) |

---

## API

All routes except `/health` require `Authorization: Bearer $API_KEY`.

| Method | Route | Description |
|--------|-------|-------------|
| `GET` | `/health` | Liveness check |
| `POST` | `/search` | Run search pipeline |
| `GET` | `/recommendations?limit=50` | Fetch stored recommendations |

---

## CLI

Run from the repo root:

```bash
uv run python -m backend.cli search "<query>" <live_limit> <sold_limit> [--no-persist] [--json] [--no-color]
```

Examples:

```bash
uv run python -m backend.cli search "margiela gats" 40 40
uv run python -m backend.cli search guidi 20 30 --no-persist
uv run python -m backend.cli search "carol christian poell" 10 10 --json
```

---

## Tests

```bash
uv run pytest
```

Test paths are configured in `pyproject.toml` (`scraper/tests`, `xscraper/tests`, `tests`).

---

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
