# xscraper

Thin X (Twitter) search scraper. Cookie-authenticated, single-page Latest
search, CLI testing harness for trend/sentiment data flows. Independent of
`backend/`, `scraper/`, and `shared/`.

## 1. One-time setup

### 1.1 Burner X account

Create a throwaway X account (or use an existing low-stakes one). This account
will be the one whose cookies xscraper uses. **Do not use your main account** —
scraping carries suspension risk.

### 1.2 Export cookies

Log in to <https://x.com> in any Chromium browser, then:

1. Open DevTools → **Application** tab → **Cookies** → `https://x.com`.
2. Find `auth_token` — copy the **Value** column.
3. Find `ct0` — copy the **Value** column.
4. Copy `xscraper/.env.example` to `xscraper/.env`:
   ```bash
   cp xscraper/.env.example xscraper/.env
   ```
5. Paste the values:
   ```env
   X_AUTH_TOKEN=<paste auth_token here>
   X_CT0=<paste ct0 here>
   ```

`xscraper/.env` is gitignored by the repo's existing `.env` rule.

## 2. Run

```bash
# from repo root
python -m xscraper.cli "margiela tabi"
python -m xscraper.cli "guidi" --limit 10
python -m xscraper.cli "carol christian poell" --json > tweets.json
```

`--limit` accepts 1–20 (single-page cap; multi-page is intentionally out of
scope for v1). Default 20.

## 3. Refreshing the GraphQL doc_id and features

X rotates `DOC_ID` and the `FEATURES` flag dict every 2–4 weeks. When this
happens, the CLI exits with code 3 and a `XSchemaError`.

To refresh:

1. Log in to x.com in DevTools.
2. Open **Network** tab. Filter by `SearchTimeline`.
3. Run a Latest search on x.com.
4. Click the SearchTimeline request.
5. **Headers** tab → Request URL: copy the path segment between
   `/graphql/` and `/SearchTimeline`. That's the new `DOC_ID`.
6. **Payload** tab → query string params → copy `features` JSON. That's the
   new `FEATURES` dict.
7. Update both constants at the top of `xscraper/graphql.py`. Update the
   "Last verified <date>" comment too.

While you're there, also capture a fresh fixture:

8. **Response** tab → right-click → Copy → Copy response →
   save to `xscraper/tests/fixtures/search_latest.json`.
9. Re-run `pytest xscraper/tests`. If `test_parse_search_response_fields`
   now fails because field values changed, update the assertions in
   `xscraper/tests/test_graphql.py` to match the new fixture.

## 4. Troubleshooting

| Exit | Symptom | Cause | Fix |
|---|---|---|---|
| 1 | `XAuthError: cookies rejected` | Burner session expired or revoked | Re-export cookies into `xscraper/.env` |
| 3 | `XSchemaError: ... DOC_ID/features likely rotated` | X rotated GraphQL constants | Follow §3 above |
| 4 | `XConfigError: X_AUTH_TOKEN must be set` | `xscraper/.env` missing or empty | Copy from `.env.example` and fill |
| 5 | `XRateLimit: rate-limited by X` | Hit per-account rate limit | Wait ~15 min or rotate burner |
| 6 | `network error: ...` | Transient httpx/network failure | Retry the command |

## 5. What's intentionally out of scope (v1)

- User profile metrics (handle is the only author field captured).
- Pagination beyond 20 results.
- `Top` / `Media` / other search products.
- Account pool rotation, sentiment scoring, persistence, backend integration.
- Playwright / browser-driven scraping.

See `docs/superpowers/specs/2026-04-27-xscraper-design.md` §14 for follow-up
work.
