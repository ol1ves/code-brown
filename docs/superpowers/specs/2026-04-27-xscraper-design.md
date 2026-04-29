# xscraper — X (Twitter) search scraper

**Date:** 2026-04-27
**Status:** Design approved, ready for implementation plan
**Owner:** Oliver

## 1. Purpose

Build a thin, self-contained X scraper for trend / market sentiment data. First milestone: enter a search term in a CLI, print the top N tweets from the **Latest** search tab. No filtering, no sentiment, no user metrics, no backend integration — this is a testing harness for a future data pipeline.

This module replaces the role of the removed `hype/` module's market-sentiment input (Reddit covers the other half, owned by another developer; intentionally no shared interface).

## 2. Scope

### In scope

- Authenticated (cookie-based) httpx client targeting X's internal GraphQL `SearchTimeline` endpoint.
- `Latest` tab only (chronological), capped at 20 tweets per call (single GraphQL page, no pagination).
- Tweet model with id, text, created_at, handle, lang, and engagement counts (like / retweet / reply / quote).
- CLI (`python -m xscraper.cli`) with positional query arg, `--limit N`, `--json` flag.
- `xscraper/.env`-scoped credentials (no shared env with `backend/`).
- Loud failure on auth / rate-limit / schema breakage. No retry.
- Unit tests against recorded JSON fixture; no live network in CI.

### Out of scope (explicitly)

- User profile / author metric scraping (deferred, but model leaves room).
- Pagination beyond a single GraphQL page (≤20 results).
- `Top` tab, `Media` tab, or other search products.
- Filtering, ranking, account-quality scoring, sentiment, formulas.
- Multi-account pool / rotation.
- Persistence to Supabase or any store.
- Integration with `backend/`, `shared/`, or the search pipeline.
- Playwright / browser-driven scraping.
- Tweet detail fetch, replies thread expansion, quote tweet expansion.

## 3. Constraints & motivations

- **2026 X scraping reality:** logged-out / guest-token search is effectively dead post-2023. Datacenter IPs are banned within ~2 requests; `doc_ids` rotate every 2–4 weeks. Authenticated cookie replay against the internal GraphQL API is the lightest viable path.
- **Iterative philosophy:** the user prefers small, comprehensible steps over a one-shot over-engineered solution. The module must be readable end-to-end in a sitting.
- **Independence:** another developer is building the Reddit path. No shared interface, no shared module, no shared env.
- **Pattern reuse (without code reuse):** the existing `scraper/` module (Grailed/Algolia, httpx + tenacity + UA rotation + payload builders + parsers) is a structural reference. `xscraper/` mirrors its layout but does not import or share code with it.

## 4. Architecture

### 4.1 Module layout

```
xscraper/
  __init__.py
  .env                    # X_AUTH_TOKEN, X_CT0, optional X_BEARER (gitignored)
  .env.example            # documents required + optional vars
  config.py               # env loader, bearer constant, headers, GraphQL URLs, default-fallback logging
  client.py               # XClient: httpx.AsyncClient w/ cookies + auth headers
  graphql.py              # SearchTimeline doc_id, variables/features builder, response parser
  models.py               # Tweet dataclass
  scraper.py              # search(query, limit) → list[Tweet]
  cli.py                  # argparse entrypoint: python -m xscraper.cli
  exceptions.py           # XAuthError, XRateLimit, XSchemaError, XConfigError
  README.md               # how to export cookies, run CLI, refresh doc_id
  tests/
    __init__.py
    test_graphql.py       # parser unit tests against recorded fixture
    test_cli.py           # CLI smoke (mocked search)
    fixtures/
      search_latest.json  # one captured GraphQL response, checked in
```

### 4.2 Separation of concerns

- **`client.py`** owns HTTP transport: opens `httpx.AsyncClient`, attaches cookies + auth headers, exposes `get_graphql(url, payload) -> dict`. Knows nothing about tweets or doc_ids.
- **`graphql.py`** owns the X protocol: doc_id constant, `variables` and `features` builders, response walker that turns a raw response into `list[Tweet]`. Knows nothing about httpx.
- **`scraper.py`** orchestrates: load config, open client, build payload, send, parse, return.
- **`cli.py`** is presentation only: argparse, `asyncio.run`, render plain or JSON.

This boundary matters because X's protocol mutates frequently (doc_ids, features). When something breaks, the maintenance change is contained in `graphql.py`.

## 5. Data flow

```
CLI (cli.py)
  parse: query, --limit, --json
  └─> asyncio.run(search(query, limit))
        │
        ▼
search() in scraper.py
  1. Config = load_config()              # config.py — reads xscraper/.env
  2. async with XClient(Config) as c:    # client.py — httpx + cookies + auth headers
  3. payload = build_search_request(query, limit)   # graphql.py
  4. raw = await c.get_graphql(SEARCH_TIMELINE_URL, payload)
  5. tweets = parse_search_response(raw)            # graphql.py → list[Tweet]
  6. return tweets[:limit]
        │
        ▼
CLI render
  --json   → json.dumps([asdict(t) for t in tweets], indent=2)
  default  → "@{handle} · {likes_compact}❤ {rts_compact}🔁 {replies_compact}💬 {quotes_compact}❝ · {created_at_iso}\n{text}\n"
```

A single `Latest`-tab GraphQL request per CLI invocation. No pagination. No state between calls.

## 6. Data model

```python
# xscraper/models.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Tweet:
    id: str               # tweet rest_id, kept as str (X ids exceed int64 in some langs)
    text: str             # full_text from legacy block
    created_at: int       # unix seconds, parsed from "Wed Apr 23 14:32:11 +0000 2026"
    handle: str           # author screen_name, no leading @
    lang: str             # "en", "ja", etc. ("" if missing)
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
```

Notes:
- `frozen=True`: tweets are immutable values.
- `created_at` as unix int aligns with the existing `ScrapeMetadata.scraped_at_unix` convention in `shared/models.py` (referenced for style consistency only; xscraper does not import shared models).
- No `Author` model in v1. When user metrics come back into scope, add `Author` and an `author: Author` field on `Tweet`.

## 7. CLI

### 7.1 Surface

```bash
python -m xscraper.cli "<query>" [--limit N] [--json]
```

- **`query`** (positional, required): search term. Quote multi-word queries.
- **`--limit N`** (int, default 20, max 20): capped at single-page size for v1. Argparse rejects out-of-range values.
- **`--json`** (flag, default false): emit JSON array of tweets instead of plain text.

### 7.2 Plain output format

One block per tweet, blank line between blocks. Counts compact-formatted (`1.2k`, `15M`):

```
@elonmusk · 1.2k❤ 340🔁 89💬 12❝ · 2026-04-26T14:32Z
just setting up my twttr
```

### 7.3 JSON output format

`json.dumps([asdict(t) for t in tweets], indent=2)`. Counts as raw ints, `created_at` as unix int.

### 7.4 Exit codes

| Code | Meaning |
|------|---------|
| 0    | success |
| 1    | `XAuthError` — cookies rejected (401/403) |
| 2    | argparse error (reserved by argparse default; do not reuse) |
| 3    | `XSchemaError` — parsing failed; doc_id likely rotated |
| 4    | `XConfigError` — required env var missing |
| 5    | `XRateLimit` — 429 |
| 6    | uncaught network/transport error (httpx) |

`cli.main` catches `XAuthError`, `XSchemaError`, `XConfigError`, `XRateLimit`, and `httpx.HTTPError` and maps each to its code above. Anything else propagates and Python exits 1 by default (collides with `XAuthError`'s code; acceptable since "unknown crash" should be loud).

## 8. Auth & request shape

### 8.1 Credentials

`xscraper/.env` (gitignored; documented in `xscraper/.env.example`):

```
X_AUTH_TOKEN=...        # required — auth_token cookie from logged-in browser
X_CT0=...               # required — ct0 cookie (CSRF token); must match auth_token's session
X_BEARER=...            # optional — overrides hardcoded web-app bearer constant
```

User exports cookies once from a logged-in burner account (DevTools → Application → Cookies → x.com). README documents the procedure step-by-step.

### 8.2 Required-vs-defaulted contract

All defaulted values **MUST** log on fallback. Silent defaults are forbidden.

- **Required (no default):** `X_AUTH_TOKEN`, `X_CT0`. Missing → log `ERROR` + raise `XConfigError` → exit 4.
- **Defaulted (logs `INFO` on fallback):** `X_BEARER`, pinned `USER_AGENT`, GraphQL `DOC_ID`. Each fallback emits its own stderr log line, e.g.:

  ```
  [xscraper.config] X_BEARER not set in env, using default web-app constant (last verified 2026-04-27)
  ```

This makes which-constants-were-in-play visible when the next breakage hits.

### 8.3 Request headers (per GraphQL call)

Built in `client.py`:

```
authorization: Bearer <X_BEARER>
x-csrf-token: <X_CT0>            # must equal ct0 cookie value
cookie: auth_token=<X_AUTH_TOKEN>; ct0=<X_CT0>
x-twitter-active-user: yes
x-twitter-auth-type: OAuth2Session
content-type: application/json
user-agent: <pinned modern Chrome UA>
accept: */*
accept-language: en-US,en;q=0.9
```

### 8.4 GraphQL endpoint

- **URL:** `https://x.com/i/api/graphql/<DOC_ID>/SearchTimeline`
- **`DOC_ID`:** module-level constant in `graphql.py` with a comment: *"X rotates this every 2–4 weeks. If `XSchemaError` fires, refresh from DevTools → Network → SearchTimeline request URL."*
- **`variables`** (JSON, sent as URL-encoded query param):
  ```json
  {
    "rawQuery": "<term>",
    "count": <limit>,
    "querySource": "typed_query",
    "product": "Latest"
  }
  ```
- **`features`:** large dict of feature flags X currently demands. Pinned literal copied from a current web-app request, stored as a const in `graphql.py`. Same rotation risk as `DOC_ID`.

### 8.5 Response parsing

Walk: `data.search_by_raw_query.search_timeline.timeline.instructions[]` → entries with `entryId` prefixed `tweet-` → `content.itemContent.tweet_results.result` → read:

- `rest_id` → `Tweet.id`
- `legacy.full_text` → `Tweet.text`
- `legacy.created_at` (parsed via `datetime.strptime` w/ format `"%a %b %d %H:%M:%S %z %Y"` — X's day-of-week-first, year-last format isn't RFC-2822 and `parsedate_to_datetime` does not handle it reliably) → `Tweet.created_at` unix int
- `legacy.lang` → `Tweet.lang`
- `legacy.favorite_count` → `Tweet.like_count`
- `legacy.retweet_count` → `Tweet.retweet_count`
- `legacy.reply_count` → `Tweet.reply_count`
- `legacy.quote_count` → `Tweet.quote_count`
- `core.user_results.result.legacy.screen_name` → `Tweet.handle`

Entries with `entryId` starting `cursor-`, `promoted-`, or anything else are skipped.

If the walker can't find the `instructions` key, or finds it but every shape lookup misses, raise `XSchemaError` (do not return an empty list — empty success is indistinguishable from broken parser).

## 9. Error handling

No retry layer. Fail fast, exit non-zero with a clear message.

| Condition | Exception | Exit | Message |
|---|---|---|---|
| `auth_token`/`ct0` missing | `XConfigError` | 4 | `"X_AUTH_TOKEN and X_CT0 must be set in xscraper/.env"` |
| HTTP 401/403 | `XAuthError` | 1 | `"cookies rejected — refresh xscraper/.env from a logged-in browser session"` |
| HTTP 429 | `XRateLimit` | 5 | `"rate-limited by X — wait or use a fresh account"` |
| HTTP 5xx / network error | `httpx.HTTPError` (re-raised) | 6 | raw httpx message |
| Response shape unrecognized | `XSchemaError` | 3 | `"SearchTimeline response shape changed — DOC_ID/features likely rotated; refresh xscraper/graphql.py from DevTools"` |

This deliberately diverges from the grailed scraper's tenacity-based retries — the user chose loud over resilient for a testing harness.

## 10. Logging

- Use stdlib `logging`. Logger names: `xscraper.config`, `xscraper.client`, `xscraper.graphql`, `xscraper.scraper`, `xscraper.cli`.
- Default level: `INFO`. `LOG_FORMAT=text` for human-readable, default JSON (mirrors `backend/logging_setup.py` posture, but xscraper does **not** import `backend.logging_setup` — it sets up its own logging in `cli.py`).
- Mandatory log lines:
  - Each defaulted-config fallback (see §8.2).
  - Search start: `INFO xscraper.scraper search start query=<q> limit=<n>`.
  - Search done: `INFO xscraper.scraper search done count=<n> elapsed_ms=<t>`.
  - On any raised exception: `ERROR` line with class + message before exit.

## 11. Testing strategy

Two test files, no live network in CI.

### 11.1 `tests/test_graphql.py`

Loads `tests/fixtures/search_latest.json` (one real captured response, checked in) and asserts:

- `parse_search_response(fixture)` returns a list of N `Tweet` instances (N = number of `tweet-` entries in fixture).
- A known tweet's fields are populated correctly (assert id, handle, text snippet, all four counts, lang, created_at unix value).
- Cursor / promoted entries are skipped.
- An empty / mangled response (`{}` or missing `instructions`) raises `XSchemaError`.

Capturing the fixture is a one-time manual step: open DevTools → Network tab → run a Latest search on x.com → right-click the `SearchTimeline` request → Copy → Copy response → save to `tests/fixtures/search_latest.json`. Documented step-by-step in `xscraper/README.md`. No CLI flag for capture — keeps the harness thin.

### 11.2 `tests/test_cli.py`

- Monkeypatch `xscraper.scraper.search` to return two synthetic `Tweet`s.
- Run CLI via `python -m xscraper.cli` (or call `cli.main` directly), capture stdout via `capsys`.
- Assert plain-format output contains both handles and text.
- Assert `--json` output is valid JSON, length 2, contains expected ids.
- Assert `--limit 0` and `--limit 21` are rejected by argparse (exit 2 — argparse default; matches the reserved slot in §7.4).

### 11.3 No tests for v1

- No live network test against X.
- No `client.py` transport test (would require vcr-recorded cassettes or live cookies — overkill for thin testing harness; revisit if scope grows).

## 12. Dependencies

No new third-party dependencies.

- `httpx` — already in `backend/requirements.txt`.
- `python-dotenv` — already in repo.
- Stdlib only otherwise: `argparse`, `asyncio`, `dataclasses`, `email.utils`, `json`, `logging`, `urllib.parse`.

## 13. Maintenance expectations

This module **will break** every 2–4 weeks. Documented breakage modes and fixes:

| Symptom | Likely cause | Fix |
|---|---|---|
| `XAuthError` exit 1 | Burner account cookies expired or session invalidated | Re-export cookies into `xscraper/.env` |
| `XSchemaError` exit 3 | `DOC_ID` rotated, or `features` dict missing a new flag | Open DevTools on x.com, run a Latest search, copy the new doc id from the Network tab URL and the updated features JSON into `graphql.py` |
| `XRateLimit` exit 2 | Per-account rate limit (~300 req/15min for SearchTimeline historically) | Wait or rotate burner |

`xscraper/README.md` mirrors this table.

## 14. Future work (not part of this spec)

The following are intentionally deferred. Each is its own follow-up spec.

- **User metrics path:** add `Author` model, fetch user-by-handle GraphQL endpoint, attach to tweets.
- **Pagination:** add `cursor` param + multi-page loop + `--limit` cap raise.
- **Account pool / rotation:** multi-account env config + per-account limit tracking, modeled on `twscrape`.
- **Persistence:** Supabase store + `--persist` CLI flag, mirroring grailed scraper's `set_store` pattern.
- **Sentiment / quality scoring:** entirely separate module that consumes `Tweet` lists.
- **Backend integration:** if/when the trends path matures, an internal-API surface for the search pipeline to call.

## 15. Open questions

None at design time. All clarifications resolved through brainstorming dialogue on 2026-04-27.
