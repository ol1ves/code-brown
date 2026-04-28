# xscraper — X (Twitter) search scraper (Playwright stealth rewrite)

**Date:** 2026-04-28
**Status:** Design approved, ready for implementation plan
**Owner:** Oliver
**Supersedes:** `docs/superpowers/specs/2026-04-27-xscraper-design.md` (httpx + cookie-replay path; deleted in commit 734c4c3 "END IT ALL")

## 1. Purpose

Rebuild `xscraper/` as a thin, self-contained X scraper using a Playwright stealth stack. Same user-facing surface as the previous spec — CLI takes a query, prints the top N tweets from the **Latest** search tab — but the transport changes from raw httpx GraphQL replay to a real, logged-in Chromium driven by `patchright`, intercepting the `SearchTimeline` GraphQL response the browser fetches for itself.

The previous httpx path failed because authenticated cookie replay against X's internal GraphQL is too brittle in 2026: header fingerprinting, `doc_id` rotation every 2–4 weeks, and silent shape changes. Letting a real browser handle auth/transport while we eavesdrop on its network responses pushes all the fragile fingerprinting onto the browser stack and leaves us with one durable concern: parsing the response shape (which we already had to do anyway).

## 2. Scope

### In scope

- `patchright` + Chromium, headless by default with `--headed` flag for debugging.
- `storage_state.json` session file written by a one-time `xscraper login` subcommand (interactive, with optional autofill from `X_USERNAME`/`X_PASSWORD` env vars).
- Single-page Latest-tab search: navigate to `https://x.com/search?q=...&f=live`, intercept the first `SearchTimeline` response, parse, return up to 20 tweets.
- Tweet model with id, text, created_at, handle, lang, and engagement counts (like / retweet / reply / quote).
- CLI (`python -m xscraper`) with `search` (default) and `login` subcommands. `-l`/`--limit` alias.
- `xscraper/.env`-scoped configuration (no shared env with `backend/`).
- Loud failure on auth / timeout / schema breakage. No retry.
- Unit tests against recorded JSON fixture; no live network in CI.

### Out of scope (explicitly)

- User profile / author metric scraping (deferred, but model leaves room).
- Pagination beyond a single GraphQL page (≤20 results).
- `Top` tab, `Media` tab, or other search products.
- Filtering, ranking, account-quality scoring, sentiment, formulas.
- Multi-account pool / rotation.
- Persistence to Supabase or any store.
- Integration with `backend/`, `shared/`, or the search pipeline.
- Tweet detail fetch, replies thread expansion, quote tweet expansion.
- DOM scraping fallback (intercept-only — if the `SearchTimeline` response doesn't fire, that's a hard failure).
- Screenshot-on-error or raw-response dumps (logs only).
- Rate-limit handling (`XRateLimit` exception). Add when observed in the wild.

## 3. Constraints & motivations

- **2026 X scraping reality (revised):** the httpx-replay path is functionally dead for sustained use. A real browser with stealth patches survives because its TLS fingerprint, JS environment, and request cadence all match a human user. `patchright` is the current-best maintained Playwright fork with stealth baked in.
- **Iterative philosophy:** small, comprehensible steps. The module must be readable end-to-end in a sitting.
- **Cross-deploy:** another dev should reach a working scrape in three commands: `uv sync`, `patchright install chromium`, `python -m xscraper login`. No per-machine config beyond `xscraper/.env`.
- **Independence:** another developer is building the Reddit path. No shared interface, no shared module, no shared env.
- **Keep the parser.** The previous spec's `graphql.py` parser remains correct — `SearchTimeline` JSON shape is the same regardless of how we obtain it. We carry the parser, fixture, and parser tests forward.

## 4. Architecture

### 4.1 Module layout

```
xscraper/
  __init__.py
  .env                  # X_USERNAME, X_PASSWORD, optional STATE_PATH, LOG_FORMAT (gitignored)
  .env.example          # documents required + optional vars
  state.json            # storage_state output, gitignored
  config.py             # env loader, state.json path, default-fallback logging
  browser.py            # patchright lifecycle, navigate + intercept SearchTimeline
  graphql.py            # SearchTimeline response parser (unchanged from prior spec)
  models.py             # Tweet dataclass
  scraper.py            # search(query, limit) → list[Tweet]
  login.py              # interactive + auto-fill login → writes state.json
  cli.py                # subcommands: search (default) | login
  exceptions.py         # XAuthError, XConfigError, XTimeoutError, XSchemaError
  README.md             # setup, login flow, fixture capture, troubleshooting
  tests/
    __init__.py
    test_graphql.py     # parser unit tests vs recorded fixture
    test_cli.py         # CLI smoke (mocked search)
    fixtures/
      search_latest.json
```

### 4.2 Separation of concerns

- **`browser.py`** owns the browser stack: launch Chromium with stealth, load `storage_state`, navigate, attach a `page.on("response")`-style listener, await the first `SearchTimeline` response, return raw JSON. Knows nothing about tweets.
- **`graphql.py`** owns the X protocol: response walker that turns a raw GraphQL response into `list[Tweet]`. Knows nothing about patchright or browsers.
- **`scraper.py`** orchestrates: load config, call browser, hand JSON to parser, return `list[Tweet]` (sliced to `limit`).
- **`login.py`** is its own surface: launch headed Chromium, optionally autofill creds, wait for the user (or autofill flow) to land on `/home`, write `state.json`. Independent of the search path.
- **`cli.py`** is presentation only: argparse subcommands, `asyncio.run`, render plain or JSON.

The `browser.py` / `graphql.py` boundary is the maintenance seam: when patchright or X's bot detection changes, `browser.py` is what moves; when X's response shape changes, `graphql.py` is what moves.

## 5. Data flow

### 5.1 Search

```
CLI (cli.py)
  parse: subcommand=search (default), query, --limit/-l, --json, --headed
  └─> asyncio.run(search(query, limit, headed=...))
        │
        ▼
search() in scraper.py
  1. config = load_config()                          # config.py — reads xscraper/.env, verifies state.json exists
  2. raw = await browser.fetch_search_timeline(query, headed=headed)
                                                     # browser.py — patchright launches, navigates, intercepts
  3. tweets = parse_search_response(raw)             # graphql.py → list[Tweet]
  4. return tweets[:limit]
        │
        ▼
CLI render
  --json   → json.dumps([asdict(t) for t in tweets], indent=2)
  default  → "@{handle} · {likes_compact}❤ {rts_compact}🔁 {replies_compact}💬 {quotes_compact}❝ · {created_at_iso}\n{text}\n"
```

A single Latest-tab navigation per CLI invocation. No pagination. No state between calls beyond `state.json`.

### 5.2 Login

```
CLI (cli.py)
  parse: subcommand=login
  └─> asyncio.run(run_login())
        │
        ▼
run_login() in login.py
  1. config = load_config()
  2. patchright.chromium.launch(headless=False)
  3. ctx = browser.new_context()                     # fresh context, no state
  4. page.goto("https://x.com/login")
  5. if X_USERNAME and X_PASSWORD set:               # autofill path
       fill username, click Next
       (optional) fill username again on suspicious-login challenge
       fill password, click Login
     else:                                           # manual path
       log: "no credentials in env — log in manually in the browser window"
  6. page.wait_for_url("https://x.com/home", timeout=5*60_000)
                                                     # covers 2FA, captcha, fully-manual — single landing wait
  7. ctx.storage_state(path=config.state_path)
  8. log: "state saved to {state_path}"
```

## 6. Data model

```python
# xscraper/models.py
from dataclasses import dataclass

@dataclass(frozen=True)
class Tweet:
    id: str
    text: str
    created_at: int       # unix seconds
    handle: str
    lang: str
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
```

Unchanged from the previous spec. `frozen=True`, ids as strings, `created_at` as unix int.

## 7. CLI

### 7.1 Surface

```bash
# search (default subcommand — keyword "search" optional)
python -m xscraper "<query>" [-l N | --limit N] [--json] [--headed]
python -m xscraper search "<query>" [-l N | --limit N] [--json] [--headed]

# login (one-time, interactive)
python -m xscraper login [--headed]
```

**Search args:**
- `query` (positional, required): search term. Quote multi-word.
- `-l` / `--limit N` (int, default 20, max 20): argparse rejects out-of-range.
- `--json` (flag, default false).
- `--headed` (flag, default false): run browser visibly.

**Login args:**
- `--headed` (flag, accepted but no-op — login is always headed by necessity).

### 7.2 Plain output format

```
@elonmusk · 1.2k❤ 340🔁 89💬 12❝ · 2026-04-26T14:32Z
just setting up my twttr
```

One block per tweet, blank line between blocks. Counts compact-formatted (`1.2k`, `15M`).

### 7.3 JSON output format

`json.dumps([asdict(t) for t in tweets], indent=2)`. Counts as raw ints, `created_at` as unix int.

### 7.4 Exit codes

| Code | Meaning |
|------|---------|
| 0    | success |
| 1    | `XAuthError` — state.json rejected (login wall hit) or login command timed out |
| 2    | argparse error (argparse default; reserved) |
| 3    | `XSchemaError` — parser missed; response shape rotated |
| 4    | `XConfigError` — required env or state.json missing |
| 5    | `XTimeoutError` — `SearchTimeline` response never fired within 30s |
| 6    | uncaught browser/transport error |

`cli.main` catches `XAuthError`, `XSchemaError`, `XConfigError`, `XTimeoutError`, and any patchright transport error and maps each to its code above.

## 8. Auth & request shape

### 8.1 Credentials & state

`xscraper/.env` (gitignored; documented in `xscraper/.env.example`):

```
X_USERNAME=        # optional — only used by `xscraper login` autofill
X_PASSWORD=        # optional — only used by `xscraper login` autofill
STATE_PATH=        # optional — defaults to xscraper/state.json
LOG_FORMAT=        # optional — "text" or "json", default "json"
```

`xscraper/state.json` is the actual authentication artifact. It's a Playwright `storage_state` snapshot containing cookies + localStorage + sessionStorage. Created by `xscraper login`. Loaded by `xscraper search` via `browser.new_context(storage_state=...)`.

**Gitignore.** Root `.gitignore` excludes `.env*` but not session files. Implementation must add `xscraper/state.json` (and `xscraper/state.*.json` for future multi-account work) to `.gitignore` before `state.json` is ever written.

### 8.2 Required-vs-defaulted contract

All defaulted values **MUST** log on fallback. Silent defaults are forbidden.

- **Required at scrape time:** `xscraper/state.json` exists on disk. Missing → log `ERROR` + raise `XConfigError` → exit 4.
- **Required at login time:** none. Without `X_USERNAME`/`X_PASSWORD`, login still works manually.
- **Defaulted (logs `INFO` on fallback):** `STATE_PATH`, `LOG_FORMAT`. Each fallback emits a stderr log line, e.g.:

  ```
  [xscraper.config] STATE_PATH not set in env, using default xscraper/state.json
  ```

### 8.3 Browser navigation

```
URL: https://x.com/search?q=<urlencoded query>&src=typed_query&f=live
Wait: page.goto(url, wait_until="domcontentloaded")
Listener: page.wait_for_response(
    lambda r: "SearchTimeline" in r.url and r.status == 200,
    timeout=30_000,
)
```

Listener attached **before** navigation to avoid races. The browser handles all headers, cookies, doc_id, features, and bot-fingerprinting on its own; we don't construct or send any request manually.

### 8.4 Response parsing

Identical to the previous spec — the response shape is independent of how we fetched it. Walk: `data.search_by_raw_query.search_timeline.timeline.instructions[]` → entries with `entryId` prefixed `tweet-` → `content.itemContent.tweet_results.result` → read:

- `rest_id` → `Tweet.id`
- `legacy.full_text` → `Tweet.text`
- `legacy.created_at` (parsed via `datetime.strptime` with format `"%a %b %d %H:%M:%S %z %Y"`) → `Tweet.created_at` unix int
- `legacy.lang` → `Tweet.lang`
- `legacy.favorite_count` → `Tweet.like_count`
- `legacy.retweet_count` → `Tweet.retweet_count`
- `legacy.reply_count` → `Tweet.reply_count`
- `legacy.quote_count` → `Tweet.quote_count`
- `core.user_results.result.legacy.screen_name` → `Tweet.handle`

Entries with `entryId` starting `cursor-`, `promoted-`, or anything else are skipped.

If the walker can't find `instructions`, or finds it but every shape lookup misses, raise `XSchemaError` (do not return an empty list — empty success is indistinguishable from broken parser).

## 9. Login flow detail

### 9.1 Headed always

Login is inherently human-shaped (captcha, 2FA, "is this you?" challenges), so the login subcommand always launches with `headless=False` regardless of the `--headed` flag. The flag is accepted for surface consistency with `search`.

### 9.2 Autofill

If `X_USERNAME` and `X_PASSWORD` are both set:

1. `page.fill('input[autocomplete="username"]', X_USERNAME)`, click Next.
2. If a "confirm your username" challenge field appears within 3s (`input[data-testid="ocfEnterTextTextInput"]`), fill it again with the same username and click Next. Otherwise skip.
3. `page.fill('input[name="password"]', X_PASSWORD)`, click `button[data-testid="LoginForm_Login_Button"]`.

If autofill silently fails (selectors changed), the headed window is right there — the user types creds manually. No exception, no exit. The single landing wait (§9.3) absorbs both paths.

### 9.3 Single landing wait

Whether autofill cruised through, the user typed everything by hand, or solved a 2FA/captcha, the success signal is the same:

```python
await page.wait_for_url("https://x.com/home", timeout=5 * 60_000)
```

5-minute timeout. On success: write `state.json`, exit 0. On timeout: log ERROR, raise `XAuthError`, exit 1 with message `"login did not complete within 5 minutes"`.

### 9.4 Output

`ctx.storage_state(path=config.state_path)`. No tokens are extracted, parsed, or stored separately. The file is opaque to xscraper — patchright reloads it as-is on the next `xscraper search`.

## 10. Error handling

No retry layer. Fail fast, exit non-zero with a clear message.

| Condition | Exception | Exit | Message |
|---|---|---|---|
| `xscraper/state.json` missing | `XConfigError` | 4 | `"xscraper/state.json not found — run \`python -m xscraper login\` first"` |
| Login wall hit (state expired) | `XAuthError` | 1 | `"state.json rejected — re-run \`python -m xscraper login\`"` |
| `SearchTimeline` response never fired in 30s | `XTimeoutError` | 5 | `"SearchTimeline response never fired within 30s"` |
| Response shape unrecognized | `XSchemaError` | 3 | `"SearchTimeline response shape changed — refresh xscraper/graphql.py parser"` |
| Login command timed out (5 min, no `/home`) | `XAuthError` | 1 | `"login did not complete within 5 minutes"` |
| Other patchright/network error | (re-raised) | 6 | raw exception message |

**Login wall detection.** If `state.json` is stale, X redirects to `/login` and `SearchTimeline` never fires. The 30s wait expires and `browser.py` checks `page.url`: if it contains `/login` or `/i/flow/login`, raise `XAuthError` (exit 1) instead of the generic `XTimeoutError` (exit 5).

**No `XRateLimit` slot.** With a real browser, 429 surfaces differently (interstitial pages, empty results). YAGNI for v1; add a slot when observed.

## 11. Logging

- Stdlib `logging`. Logger names: `xscraper.config`, `xscraper.browser`, `xscraper.graphql`, `xscraper.scraper`, `xscraper.login`, `xscraper.cli`.
- Default level: `INFO`. `LOG_FORMAT=text` for human-readable, default JSON.
- Mandatory log lines:
  - Each defaulted-config fallback (see §8.2).
  - Search start: `INFO xscraper.scraper search start query=<q> limit=<n>`.
  - Search done: `INFO xscraper.scraper search done count=<n> elapsed_ms=<t>`.
  - Login start: `INFO xscraper.login login start autofill=<bool>`.
  - Login done: `INFO xscraper.login state saved to <path>`.
  - On any raised exception: `ERROR` line with class + message before exit.
- **No screenshot-on-error, no raw-response dump.** Logs only.

## 12. Testing strategy

Two test files, no live network in CI.

### 12.1 `tests/test_graphql.py`

Loads `tests/fixtures/search_latest.json` (one real captured `SearchTimeline` response, checked in) and asserts:

- `parse_search_response(fixture)` returns a list of N `Tweet` instances (N = number of `tweet-` entries in fixture).
- A known tweet's fields are populated correctly (id, handle, text snippet, all four counts, lang, created_at unix value).
- Cursor / promoted entries are skipped.
- An empty / mangled response (`{}` or missing `instructions`) raises `XSchemaError`.

Capturing the fixture is a one-time manual step: open DevTools → Network tab → run a Latest search on x.com → right-click the `SearchTimeline` request → Copy → Copy response → save to `tests/fixtures/search_latest.json`. Documented step-by-step in `xscraper/README.md`.

### 12.2 `tests/test_cli.py`

- Monkeypatch `xscraper.scraper.search` to return two synthetic `Tweet`s.
- Run CLI via `python -m xscraper` (or call `cli.main` directly), capture stdout via `capsys`.
- Assert plain-format output contains both handles and text.
- Assert `--json` output is valid JSON, length 2, contains expected ids.
- Assert `-l 0` and `-l 21` are rejected by argparse (exit 2).
- Assert default subcommand resolution (`xscraper "q"` ≡ `xscraper search "q"`).

### 12.3 No tests for v1

- No live network test against X.
- No `browser.py` test — patchright wrapper too thin to mock meaningfully; integration is "run it on a fresh machine."
- No `login.py` test — same reasoning, plus headed-only flow doesn't fit unit-test shape.

## 13. Dependencies

- **New:** `patchright` — added to root `pyproject.toml`.
- **Reused:** `python-dotenv` (already in repo). Stdlib otherwise: `argparse`, `asyncio`, `dataclasses`, `json`, `logging`, `urllib.parse`, `pathlib`.
- **One-time machine setup** (documented in `xscraper/README.md`):

  ```bash
  uv sync
  patchright install chromium
  python -m xscraper login         # opens browser, log in once, writes state.json
  python -m xscraper "test query"  # verify
  ```

## 14. Maintenance expectations

This module **will break** periodically. Documented breakage modes and fixes:

| Symptom | Likely cause | Fix |
|---|---|---|
| `XAuthError` exit 1 (scrape) | `state.json` expired or session invalidated | Re-run `python -m xscraper login` |
| `XSchemaError` exit 3 | X response shape changed | Capture fresh `SearchTimeline` JSON, update `graphql.py` parser, refresh fixture |
| `XTimeoutError` exit 5 | X is slow, stealth detection tripped, or patchright Chromium needs update | First retry; if persistent, run `--headed` and watch — could be a bot challenge wall |
| Login autofill silently does nothing | X form selector rotted | Type credentials manually in the open window; update `login.py` selectors |
| Login command times out | 2FA challenge unsolved, or `/home` URL no longer the post-login landing | Manually verify the post-login URL in browser, update `wait_for_url` target |

`xscraper/README.md` mirrors this table.

## 15. Future work (not part of this spec)

The following are intentionally deferred. Each is its own follow-up spec.

- **User metrics path:** add `Author` model, attach to tweets.
- **Pagination:** scroll-driven multi-response collection + `--limit` cap raise.
- **Account pool / rotation:** multiple `state.json` files, per-account limit tracking.
- **Persistence:** Supabase store + `--persist` CLI flag.
- **Sentiment / quality scoring:** entirely separate module that consumes `Tweet` lists.
- **Backend integration:** internal-API surface for the search pipeline to call.
- **Rate-limit handling:** add `XRateLimit` slot when 429 symptoms observed in the wild.
- **Debug artifacts:** screenshot-on-error and raw-response dumps to `xscraper/debug/`.

## 16. Open questions

None at design time. All clarifications resolved through brainstorming dialogue on 2026-04-28.
