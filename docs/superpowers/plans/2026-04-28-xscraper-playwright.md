# xscraper Playwright Stealth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `xscraper/` as a CLI that drives a logged-in `patchright` Chromium browser, intercepts X's `SearchTimeline` GraphQL response, parses it into `Tweet` objects, and renders them. Same user-facing surface as the deleted httpx version (commit 734c4c3); transport changed to a real browser to survive bot detection.

**Architecture:** `patchright.async_api` Chromium (headless by default) with `storage_state.json` session → navigate to `https://x.com/search?q=…&f=live` → `page.wait_for_response` listener catches the first `SearchTimeline` response → parse `legacy` blocks into `Tweet` dataclasses → render plain or `--json` to stdout. One-time `xscraper login` subcommand writes the session file (autofill from `X_USERNAME`/`X_PASSWORD`, manual fallback). Spec at [docs/superpowers/specs/2026-04-28-xscraper-playwright-design.md](../specs/2026-04-28-xscraper-playwright-design.md).

**Tech Stack:** Python 3.14+, `patchright` (async Playwright fork w/ stealth), `python-dotenv`, stdlib `argparse`/`asyncio`/`logging`/`dataclasses`/`urllib.parse`. Tests use `pytest` + monkeypatching (no live network, no patchright in unit tests).

---

## File Structure

To be created:

| File | Responsibility |
|---|---|
| `xscraper/__init__.py` | Package marker. Empty. |
| `xscraper/__main__.py` | One-liner so `python -m xscraper` runs `cli.main()`. |
| `xscraper/.env.example` | Documents `X_USERNAME`, `X_PASSWORD`, `STATE_PATH`, `LOG_FORMAT`. |
| `xscraper/exceptions.py` | `XError` base + `XConfigError`, `XAuthError`, `XTimeoutError`, `XSchemaError`. |
| `xscraper/models.py` | `Tweet` frozen dataclass. |
| `xscraper/config.py` | Env loading w/ default-fallback logging. `Config` dataclass. State path resolution. Logging setup. |
| `xscraper/graphql.py` | `parse_search_response(raw) -> list[Tweet]`. Walks `legacy` blocks. |
| `xscraper/browser.py` | `fetch_search_timeline(query, *, headed) -> dict`: launches patchright Chromium, navigates, intercepts response. |
| `xscraper/login.py` | `run_login(*, headed)`: launches headed Chromium, optional autofill, single landing wait, writes `state.json`. |
| `xscraper/scraper.py` | `search(query, limit, *, headed) -> list[Tweet]` orchestrator. |
| `xscraper/cli.py` | argparse subcommands (`search` default, `login`), async entry, plain + JSON renderers. |
| `xscraper/README.md` | Setup, login flow, fixture capture, troubleshooting. |
| `xscraper/tests/__init__.py` | Empty. |
| `xscraper/tests/conftest.py` | `load_fixture` helper. |
| `xscraper/tests/fixtures/search_latest.json` | Hand-crafted minimal SearchTimeline response (one tweet, one cursor). Replaced by real captured response in Task 12. |
| `xscraper/tests/test_exceptions.py` | Exception hierarchy tests. |
| `xscraper/tests/test_models.py` | `Tweet` dataclass tests. |
| `xscraper/tests/test_config.py` | Env loader + state-path + default-fallback log tests. |
| `xscraper/tests/test_graphql.py` | Parser tests against fixture. |
| `xscraper/tests/test_scraper.py` | Orchestrator test w/ monkeypatched browser. |
| `xscraper/tests/test_cli.py` | CLI tests w/ monkeypatched `search` + `run_login`. |

To be modified:

| File | Change |
|---|---|
| `pyproject.toml` | `xscraper/tests` already in `testpaths` — verify. |
| `.gitignore` | Add `xscraper/state.json` and `xscraper/state.*.json`. |
| `backend/requirements.txt` | Add `patchright` (alphabetical, between `pandas` and `pluggy`). |

**Dependency note.** Spec §13 says "patchright in root `pyproject.toml`". The repo's actual Python dep source of truth is `backend/requirements.txt` — root `pyproject.toml` has no `[project]` section. We add `patchright` to `backend/requirements.txt`. The `patchright install chromium` step (downloads the Chromium binary) is documented in `xscraper/README.md`, not automated.

---

## Task 1: Scaffold + dependencies + gitignore

**Files:**
- Create: `xscraper/__init__.py`
- Create: `xscraper/__main__.py`
- Create: `xscraper/.env.example`
- Create: `xscraper/tests/__init__.py`
- Create: `xscraper/tests/conftest.py`
- Modify: `.gitignore`
- Modify: `backend/requirements.txt`
- Verify: `pyproject.toml`

- [ ] **Step 1: Create empty package files**

```bash
mkdir -p xscraper/tests/fixtures
touch xscraper/__init__.py xscraper/tests/__init__.py
```

- [ ] **Step 2: Create `xscraper/__main__.py`**

```python
"""Entry point for ``python -m xscraper``."""

from xscraper.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Create `xscraper/.env.example`**

```env
# Optional. Used only by `python -m xscraper login` to autofill the X login form.
# Without these the login command opens a browser and waits for you to type in.
X_USERNAME=
X_PASSWORD=

# Optional. Path to the patchright storage_state file (cookies + localStorage).
# Default: xscraper/state.json
# STATE_PATH=

# Optional. "json" (default) or "text" for stderr logs.
# LOG_FORMAT=
```

- [ ] **Step 4: Create `xscraper/tests/conftest.py`**

```python
"""Shared pytest fixtures for xscraper tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def load_fixture():
    def _load(name: str) -> dict:
        return json.loads((FIXTURES_DIR / name).read_text())

    return _load
```

- [ ] **Step 5: Add `state.json` patterns to `.gitignore`**

Open `.gitignore`. Find the section ending with `# Local runtime data` and append after the `*.sqlite3` line, before the `.claude/` line. Final block should read:

```gitignore
# Local runtime data
tmp/
temp/
*.sqlite
*.sqlite3

# xscraper session state (patchright storage_state)
xscraper/state.json
xscraper/state.*.json

.claude/
```

- [ ] **Step 6: Add `patchright` to `backend/requirements.txt`**

Open `backend/requirements.txt`. Insert `patchright` on its own line in alphabetical order (between `pandas==3.0.2` and `pluggy==1.6.0`). Use no version pin — patchright is moving fast and we want fresh stealth patches:

```
pandas==3.0.2
patchright
pluggy==1.6.0
```

- [ ] **Step 7: Verify `pyproject.toml` testpaths already include `xscraper/tests`**

Run: `grep testpaths pyproject.toml`
Expected: `testpaths = ["scraper/tests", "tests", "xscraper/tests"]`

If `xscraper/tests` is missing, add it. (It's already there from the previous attempt; this is a sanity check.)

- [ ] **Step 8: Install `patchright` and the Chromium binary in the active venv**

```bash
.venv/bin/pip install patchright
.venv/bin/patchright install chromium
```

Expected: `patchright` installs from PyPI; `patchright install chromium` downloads the patched Chromium build (~150 MB, takes ~30s).

- [ ] **Step 9: Verify pytest discovers the new path**

Run: `.venv/bin/pytest xscraper/tests --collect-only`
Expected: `no tests ran` (no test files yet) — must NOT error on path resolution.

- [ ] **Step 10: Commit**

```bash
git add xscraper/__init__.py xscraper/__main__.py xscraper/.env.example xscraper/tests/__init__.py xscraper/tests/conftest.py .gitignore backend/requirements.txt
git commit -m "feat(xscraper): scaffold module skeleton and add patchright dep"
```

---

## Task 2: Exceptions

**Files:**
- Create: `xscraper/exceptions.py`
- Create: `xscraper/tests/test_exceptions.py`

- [ ] **Step 1: Write failing test**

`xscraper/tests/test_exceptions.py`:

```python
"""Exception hierarchy unit tests."""

from __future__ import annotations

import pytest

from xscraper.exceptions import (
    XAuthError,
    XConfigError,
    XError,
    XSchemaError,
    XTimeoutError,
)


@pytest.mark.parametrize(
    "cls",
    [XConfigError, XAuthError, XTimeoutError, XSchemaError],
)
def test_subclass_of_xerror(cls):
    assert issubclass(cls, XError)
    assert issubclass(XError, Exception)


def test_messages_propagate():
    with pytest.raises(XAuthError, match="bad state"):
        raise XAuthError("bad state")
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/pytest xscraper/tests/test_exceptions.py -v`
Expected: `ModuleNotFoundError: No module named 'xscraper.exceptions'`.

- [ ] **Step 3: Implement `xscraper/exceptions.py`**

```python
"""xscraper-specific exceptions.

Each maps to a distinct CLI exit code in xscraper/cli.py:
  XAuthError    -> 1
  XSchemaError  -> 3
  XConfigError  -> 4
  XTimeoutError -> 5
"""

from __future__ import annotations


class XError(Exception):
    """Base for all xscraper errors."""


class XConfigError(XError):
    """Required env or state.json missing."""


class XAuthError(XError):
    """X rejected our session (login wall hit) or login flow timed out."""


class XTimeoutError(XError):
    """SearchTimeline response never fired within the wait window."""


class XSchemaError(XError):
    """Response shape unrecognized; X's GraphQL response shape changed."""
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/pytest xscraper/tests/test_exceptions.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add xscraper/exceptions.py xscraper/tests/test_exceptions.py
git commit -m "feat(xscraper): add exception hierarchy"
```

---

## Task 3: Tweet model

**Files:**
- Create: `xscraper/models.py`
- Create: `xscraper/tests/test_models.py`

- [ ] **Step 1: Write failing test**

`xscraper/tests/test_models.py`:

```python
"""Tweet dataclass tests."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

import pytest

from xscraper.models import Tweet


def _sample() -> Tweet:
    return Tweet(
        id="1234567890",
        text="hello world",
        created_at=1714056731,
        handle="testuser",
        lang="en",
        like_count=42,
        retweet_count=7,
        reply_count=3,
        quote_count=1,
    )


def test_fields_set_correctly():
    t = _sample()
    assert t.id == "1234567890"
    assert t.text == "hello world"
    assert t.created_at == 1714056731
    assert t.handle == "testuser"
    assert t.lang == "en"
    assert t.like_count == 42
    assert t.retweet_count == 7
    assert t.reply_count == 3
    assert t.quote_count == 1


def test_is_frozen():
    t = _sample()
    with pytest.raises(FrozenInstanceError):
        t.text = "mutated"  # type: ignore[misc]


def test_asdict_roundtrip():
    t = _sample()
    d = asdict(t)
    assert d["id"] == "1234567890"
    assert d["like_count"] == 42
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/pytest xscraper/tests/test_models.py -v`
Expected: `ModuleNotFoundError: No module named 'xscraper.models'`.

- [ ] **Step 3: Implement `xscraper/models.py`**

```python
"""Tweet value object. Frozen — tweets are immutable snapshots."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tweet:
    id: str
    text: str
    created_at: int  # unix seconds
    handle: str
    lang: str
    like_count: int
    retweet_count: int
    reply_count: int
    quote_count: int
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/pytest xscraper/tests/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add xscraper/models.py xscraper/tests/test_models.py
git commit -m "feat(xscraper): add Tweet dataclass"
```

---

## Task 4: Config

**Files:**
- Create: `xscraper/config.py`
- Create: `xscraper/tests/test_config.py`

`config.py` does three things: load env vars from `xscraper/.env`, resolve `state.json` path with default-fallback logging, and provide a `setup_logging()` helper. It does **not** verify `state.json` exists yet — that's the scraper's job (Task 8) to fail loudly with `XConfigError` only when actually needed.

- [ ] **Step 1: Write failing test**

`xscraper/tests/test_config.py`:

```python
"""Config loader tests."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from xscraper.config import Config, load_config, setup_logging


def test_defaults_when_env_empty(monkeypatch, caplog, tmp_path):
    monkeypatch.delenv("X_USERNAME", raising=False)
    monkeypatch.delenv("X_PASSWORD", raising=False)
    monkeypatch.delenv("STATE_PATH", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.INFO, logger="xscraper.config"):
        cfg = load_config()

    assert cfg.x_username is None
    assert cfg.x_password is None
    assert cfg.state_path == Path("xscraper/state.json")
    assert cfg.log_format == "json"
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "STATE_PATH not set" in msgs
    assert "LOG_FORMAT not set" in msgs


def test_envs_used_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("X_USERNAME", "alice")
    monkeypatch.setenv("X_PASSWORD", "secret")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "custom.json"))
    monkeypatch.setenv("LOG_FORMAT", "text")

    cfg = load_config()

    assert cfg.x_username == "alice"
    assert cfg.x_password == "secret"
    assert cfg.state_path == tmp_path / "custom.json"
    assert cfg.log_format == "text"


def test_setup_logging_does_not_raise():
    setup_logging("json")
    setup_logging("text")
    # No assertion — we just want to make sure neither path raises.


def test_config_is_a_dataclass():
    cfg = Config(
        x_username=None,
        x_password=None,
        state_path=Path("x.json"),
        log_format="json",
    )
    assert cfg.state_path == Path("x.json")
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/pytest xscraper/tests/test_config.py -v`
Expected: `ModuleNotFoundError: No module named 'xscraper.config'`.

- [ ] **Step 3: Implement `xscraper/config.py`**

```python
"""Env loading, state-path resolution, and logging setup for xscraper.

Reads xscraper/.env on import via python-dotenv. All defaulted values log on
fallback — silent defaults are forbidden (see spec §8.2).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

# Load xscraper/.env into os.environ. Idempotent and safe to call repeatedly.
_DOTENV_PATH = Path(__file__).parent / ".env"
load_dotenv(_DOTENV_PATH, override=False)

log = logging.getLogger("xscraper.config")

_DEFAULT_STATE_PATH = Path("xscraper/state.json")
_DEFAULT_LOG_FORMAT = "json"


@dataclass(frozen=True)
class Config:
    x_username: str | None
    x_password: str | None
    state_path: Path
    log_format: str  # "json" or "text"


def load_config() -> Config:
    """Read env vars, log fallbacks, return a frozen Config."""
    raw_state = os.environ.get("STATE_PATH")
    if raw_state:
        state_path = Path(raw_state)
    else:
        log.info(
            "STATE_PATH not set in env, using default %s", _DEFAULT_STATE_PATH
        )
        state_path = _DEFAULT_STATE_PATH

    raw_fmt = os.environ.get("LOG_FORMAT")
    if raw_fmt:
        log_format = raw_fmt.lower()
    else:
        log.info(
            "LOG_FORMAT not set in env, using default %s", _DEFAULT_LOG_FORMAT
        )
        log_format = _DEFAULT_LOG_FORMAT

    return Config(
        x_username=os.environ.get("X_USERNAME") or None,
        x_password=os.environ.get("X_PASSWORD") or None,
        state_path=state_path,
        log_format=log_format,
    )


class _JsonFormatter(logging.Formatter):
    """Minimal JSON log formatter — single-line per record."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def setup_logging(log_format: str) -> None:
    """Configure stderr logging for xscraper. Idempotent."""
    root = logging.getLogger("xscraper")
    root.setLevel(logging.INFO)
    # Remove any handlers we previously installed so re-runs (tests) are clean.
    for h in list(root.handlers):
        root.removeHandler(h)
    handler = logging.StreamHandler(sys.stderr)
    if log_format == "text":
        handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s %(message)s")
        )
    else:
        handler.setFormatter(_JsonFormatter())
    root.addHandler(handler)
    root.propagate = False
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/pytest xscraper/tests/test_config.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add xscraper/config.py xscraper/tests/test_config.py
git commit -m "feat(xscraper): add config loader with default-fallback logging"
```

---

## Task 5: Hand-crafted fixture for parser tests

**Files:**
- Create: `xscraper/tests/fixtures/search_latest.json`

This is a stand-in until a real `SearchTimeline` response is captured (Task 12). Hand-crafted to exercise: one tweet entry, one cursor entry (must be skipped), correct nesting under `data.search_by_raw_query.search_timeline.timeline.instructions`.

- [ ] **Step 1: Create the fixture file**

`xscraper/tests/fixtures/search_latest.json`:

```json
{
  "data": {
    "search_by_raw_query": {
      "search_timeline": {
        "timeline": {
          "instructions": [
            {
              "type": "TimelineAddEntries",
              "entries": [
                {
                  "entryId": "tweet-1234567890123456789",
                  "content": {
                    "itemContent": {
                      "tweet_results": {
                        "result": {
                          "rest_id": "1234567890123456789",
                          "core": {
                            "user_results": {
                              "result": {
                                "legacy": {
                                  "screen_name": "testuser"
                                }
                              }
                            }
                          },
                          "legacy": {
                            "full_text": "hello world",
                            "created_at": "Wed Apr 23 14:32:11 +0000 2026",
                            "lang": "en",
                            "favorite_count": 42,
                            "retweet_count": 7,
                            "reply_count": 3,
                            "quote_count": 1
                          }
                        }
                      }
                    }
                  }
                },
                {
                  "entryId": "cursor-bottom-foo",
                  "content": {"cursorType": "Bottom", "value": "foo"}
                }
              ]
            }
          ]
        }
      }
    }
  }
}
```

- [ ] **Step 2: Verify the fixture is valid JSON**

Run: `python -c "import json; json.load(open('xscraper/tests/fixtures/search_latest.json'))"`
Expected: no output, exit 0.

- [ ] **Step 3: Commit**

```bash
git add xscraper/tests/fixtures/search_latest.json
git commit -m "test(xscraper): add hand-crafted SearchTimeline fixture"
```

---

## Task 6: GraphQL response parser

**Files:**
- Create: `xscraper/graphql.py`
- Create: `xscraper/tests/test_graphql.py`

The parser walks `data.search_by_raw_query.search_timeline.timeline.instructions[]`, picks `tweet-` entries, skips `cursor-`/`promoted-`/other, and reads `legacy` fields. X's `created_at` format is non-RFC ("Wed Apr 23 14:32:11 +0000 2026") so `strptime` is the right tool, not `email.utils.parsedate_to_datetime`.

- [ ] **Step 1: Write failing test**

`xscraper/tests/test_graphql.py`:

```python
"""SearchTimeline parser tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from xscraper.exceptions import XSchemaError
from xscraper.graphql import parse_search_response


def test_parse_returns_one_tweet(load_fixture):
    raw = load_fixture("search_latest.json")
    tweets = parse_search_response(raw)
    assert len(tweets) == 1


def test_tweet_fields_populated(load_fixture):
    raw = load_fixture("search_latest.json")
    [t] = parse_search_response(raw)
    assert t.id == "1234567890123456789"
    assert t.text == "hello world"
    assert t.handle == "testuser"
    assert t.lang == "en"
    assert t.like_count == 42
    assert t.retweet_count == 7
    assert t.reply_count == 3
    assert t.quote_count == 1
    expected = int(
        datetime(2026, 4, 23, 14, 32, 11, tzinfo=timezone.utc).timestamp()
    )
    assert t.created_at == expected


def test_cursor_entries_skipped(load_fixture):
    # Fixture has one cursor- entry; final list size confirms it was skipped.
    raw = load_fixture("search_latest.json")
    tweets = parse_search_response(raw)
    handles = {t.handle for t in tweets}
    assert handles == {"testuser"}


def test_empty_response_raises_schema_error():
    with pytest.raises(XSchemaError):
        parse_search_response({})


def test_missing_instructions_raises_schema_error():
    bad = {"data": {"search_by_raw_query": {"search_timeline": {"timeline": {}}}}}
    with pytest.raises(XSchemaError):
        parse_search_response(bad)


def test_no_tweet_entries_raises_schema_error():
    """An empty entries list is indistinguishable from a broken parser; raise."""
    bad = {
        "data": {
            "search_by_raw_query": {
                "search_timeline": {
                    "timeline": {
                        "instructions": [
                            {"type": "TimelineAddEntries", "entries": []}
                        ]
                    }
                }
            }
        }
    }
    with pytest.raises(XSchemaError):
        parse_search_response(bad)
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/pytest xscraper/tests/test_graphql.py -v`
Expected: `ModuleNotFoundError: No module named 'xscraper.graphql'`.

- [ ] **Step 3: Implement `xscraper/graphql.py`**

```python
"""SearchTimeline response parser.

This is the most fragile file in xscraper alongside browser.py. X's GraphQL
response shape rotates periodically. When XSchemaError fires, capture a fresh
SearchTimeline response from DevTools and update both this parser and the
fixture in xscraper/tests/fixtures/search_latest.json.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from xscraper.exceptions import XSchemaError
from xscraper.models import Tweet

# X's created_at format: "Wed Apr 23 14:32:11 +0000 2026" — non-RFC, day-of-week
# first, year last. email.utils.parsedate_to_datetime does not handle this
# reliably; strptime does.
_X_TS_FORMAT = "%a %b %d %H:%M:%S %z %Y"


def parse_search_response(raw: dict[str, Any]) -> list[Tweet]:
    """Walk the SearchTimeline response and return list[Tweet].

    Raises XSchemaError if the shape is unrecognized OR if no tweet entries
    are found (empty success would be indistinguishable from a broken parser).
    """
    try:
        instructions = raw["data"]["search_by_raw_query"]["search_timeline"][
            "timeline"
        ]["instructions"]
    except (KeyError, TypeError) as exc:
        raise XSchemaError(
            "SearchTimeline response missing data.search_by_raw_query."
            "search_timeline.timeline.instructions — response shape changed; "
            "refresh xscraper/graphql.py parser"
        ) from exc

    if not isinstance(instructions, list):
        raise XSchemaError("instructions is not a list")

    tweets: list[Tweet] = []
    for instruction in instructions:
        if not isinstance(instruction, dict):
            continue
        entries = instruction.get("entries")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            tweet = _entry_to_tweet(entry)
            if tweet is not None:
                tweets.append(tweet)

    if not tweets:
        raise XSchemaError(
            "SearchTimeline response had instructions but no parseable tweet "
            "entries — response shape changed; refresh xscraper/graphql.py parser"
        )
    return tweets


def _entry_to_tweet(entry: Any) -> Tweet | None:
    """Convert a single timeline entry to a Tweet, or None to skip it."""
    if not isinstance(entry, dict):
        return None
    entry_id = entry.get("entryId", "")
    if not entry_id.startswith("tweet-"):
        return None  # cursor-, promoted-, anything else: skip silently
    try:
        result = entry["content"]["itemContent"]["tweet_results"]["result"]
        legacy = result["legacy"]
        user_legacy = result["core"]["user_results"]["result"]["legacy"]
        return Tweet(
            id=str(result["rest_id"]),
            text=legacy["full_text"],
            created_at=int(
                datetime.strptime(
                    legacy["created_at"], _X_TS_FORMAT
                ).timestamp()
            ),
            handle=user_legacy["screen_name"],
            lang=legacy.get("lang", "") or "",
            like_count=int(legacy["favorite_count"]),
            retweet_count=int(legacy["retweet_count"]),
            reply_count=int(legacy["reply_count"]),
            quote_count=int(legacy["quote_count"]),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise XSchemaError(
            f"failed to parse tweet entry {entry_id!r}: {exc}"
        ) from exc
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/pytest xscraper/tests/test_graphql.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add xscraper/graphql.py xscraper/tests/test_graphql.py
git commit -m "feat(xscraper): add SearchTimeline response parser"
```

---

## Task 7: Browser layer (`browser.py`)

**Files:**
- Create: `xscraper/browser.py`

No unit tests for this file (spec §12.3): patchright wrappers are too thin to mock meaningfully. Verification is the end-to-end smoke test in Task 12. Keep this file under ~80 lines.

- [ ] **Step 1: Implement `xscraper/browser.py`**

```python
"""Browser transport: drive a logged-in patchright Chromium and return the raw
SearchTimeline GraphQL response.

The browser handles all auth, headers, cookies, doc_id, features, and TLS
fingerprinting on its own. We attach a response listener BEFORE navigating so
we don't race the request, then return whatever JSON the browser fetched for
itself. Knows nothing about Tweet or any GraphQL shape.
"""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.parse import quote

from patchright.async_api import async_playwright
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from xscraper.exceptions import XAuthError, XConfigError, XTimeoutError

log = logging.getLogger("xscraper.browser")

_SEARCH_URL_TEMPLATE = "https://x.com/search?q={q}&src=typed_query&f=live"
_RESPONSE_TIMEOUT_MS = 30_000
_LOGIN_URL_MARKERS = ("/login", "/i/flow/login")


async def fetch_search_timeline(
    query: str, *, state_path: Path, headed: bool = False
) -> dict:
    """Navigate to the Latest search tab and return the first SearchTimeline JSON.

    Raises:
      XConfigError    if state_path does not exist on disk.
      XAuthError      if the response never fires AND the page is on a login URL.
      XTimeoutError   if the response never fires AND we are not on a login URL.
    """
    if not state_path.exists():
        raise XConfigError(
            f"{state_path} not found — run `python -m xscraper login` first"
        )

    url = _SEARCH_URL_TEMPLATE.format(q=quote(query, safe=""))
    log.info("launching chromium headed=%s", headed)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=not headed)
        try:
            ctx = await browser.new_context(storage_state=str(state_path))
            page = await ctx.new_page()

            # Attach the listener BEFORE goto() so we don't race the request.
            response_promise = page.wait_for_response(
                lambda r: "SearchTimeline" in r.url and r.status == 200,
                timeout=_RESPONSE_TIMEOUT_MS,
            )
            await page.goto(url, wait_until="domcontentloaded")

            try:
                response = await response_promise
            except PlaywrightTimeoutError as exc:
                current = page.url
                if any(m in current for m in _LOGIN_URL_MARKERS):
                    raise XAuthError(
                        "state.json rejected — re-run "
                        "`python -m xscraper login`"
                    ) from exc
                raise XTimeoutError(
                    "SearchTimeline response never fired within 30s"
                ) from exc

            return await response.json()
        finally:
            await browser.close()
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `.venv/bin/python -c "from xscraper.browser import fetch_search_timeline; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add xscraper/browser.py
git commit -m "feat(xscraper): add patchright browser transport"
```

---

## Task 8: Search orchestrator (`scraper.py`)

**Files:**
- Create: `xscraper/scraper.py`
- Create: `xscraper/tests/test_scraper.py`

`search()` is the public coroutine the CLI calls. It loads config, calls the browser, hands the JSON to the parser, slices to `limit`. Tests monkeypatch `browser.fetch_search_timeline` so no patchright is involved.

- [ ] **Step 1: Write failing test**

`xscraper/tests/test_scraper.py`:

```python
"""scraper.search orchestrator tests (browser monkeypatched)."""

from __future__ import annotations

import pytest

from xscraper import scraper
from xscraper.exceptions import XConfigError


@pytest.mark.asyncio
async def test_search_returns_parsed_tweets(monkeypatch, load_fixture, tmp_path):
    # Pretend state.json exists.
    state = tmp_path / "state.json"
    state.write_text("{}")
    monkeypatch.setenv("STATE_PATH", str(state))

    raw = load_fixture("search_latest.json")

    async def fake_fetch(query, *, state_path, headed):
        assert query == "macbook"
        assert state_path == state
        assert headed is False
        return raw

    monkeypatch.setattr(scraper, "fetch_search_timeline", fake_fetch)

    tweets = await scraper.search("macbook", 20, headed=False)
    assert len(tweets) == 1
    assert tweets[0].handle == "testuser"


@pytest.mark.asyncio
async def test_search_slices_to_limit(monkeypatch, load_fixture, tmp_path):
    state = tmp_path / "state.json"
    state.write_text("{}")
    monkeypatch.setenv("STATE_PATH", str(state))

    raw = load_fixture("search_latest.json")

    async def fake_fetch(query, *, state_path, headed):
        return raw

    monkeypatch.setattr(scraper, "fetch_search_timeline", fake_fetch)
    tweets = await scraper.search("macbook", 0, headed=False)
    assert tweets == []


@pytest.mark.asyncio
async def test_search_raises_when_state_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "nope.json"))

    # Don't even need to monkeypatch fetch_search_timeline — config check is
    # actually performed inside fetch_search_timeline; we still expect it to
    # raise XConfigError before any patchright work happens.

    async def fake_fetch(query, *, state_path, headed):
        # Simulate the real check that browser.py performs.
        from xscraper.exceptions import XConfigError

        raise XConfigError(f"{state_path} not found")

    monkeypatch.setattr(scraper, "fetch_search_timeline", fake_fetch)

    with pytest.raises(XConfigError):
        await scraper.search("macbook", 20, headed=False)
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/pytest xscraper/tests/test_scraper.py -v`
Expected: `ModuleNotFoundError: No module named 'xscraper.scraper'`.

- [ ] **Step 3: Implement `xscraper/scraper.py`**

```python
"""Search orchestrator. CLI's only entry into the data path."""

from __future__ import annotations

import logging
import time

from xscraper.browser import fetch_search_timeline
from xscraper.config import load_config
from xscraper.graphql import parse_search_response
from xscraper.models import Tweet

log = logging.getLogger("xscraper.scraper")


async def search(query: str, limit: int, *, headed: bool = False) -> list[Tweet]:
    """Run one Latest-tab search and return up to ``limit`` Tweet objects."""
    cfg = load_config()
    log.info("search start query=%r limit=%d", query, limit)
    started = time.monotonic()

    raw = await fetch_search_timeline(
        query, state_path=cfg.state_path, headed=headed
    )
    tweets = parse_search_response(raw)
    sliced = tweets[:limit]

    elapsed_ms = int((time.monotonic() - started) * 1000)
    log.info(
        "search done count=%d elapsed_ms=%d", len(sliced), elapsed_ms
    )
    return sliced
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/pytest xscraper/tests/test_scraper.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add xscraper/scraper.py xscraper/tests/test_scraper.py
git commit -m "feat(xscraper): add search orchestrator"
```

---

## Task 9: Login command (`login.py`)

**Files:**
- Create: `xscraper/login.py`

No unit tests (spec §12.3). Headed-only browser flow doesn't fit unit-test shape; integration is "run it on a fresh machine, log in, see state.json appear."

- [ ] **Step 1: Implement `xscraper/login.py`**

```python
"""One-time login helper. Writes patchright storage_state to disk so subsequent
`python -m xscraper search` runs can reuse the session.

Always headed — login is inherently human-shaped (captcha, 2FA, "is this you?"
challenges). When X_USERNAME and X_PASSWORD are present, autofills the form;
otherwise the user types creds in the open window. Either way, the success
signal is the same: page lands on https://x.com/home within 5 minutes.
"""

from __future__ import annotations

import logging

from patchright.async_api import async_playwright
from patchright.async_api import TimeoutError as PlaywrightTimeoutError

from xscraper.config import load_config
from xscraper.exceptions import XAuthError

log = logging.getLogger("xscraper.login")

_LOGIN_URL = "https://x.com/login"
_HOME_URL = "https://x.com/home"
_LANDING_TIMEOUT_MS = 5 * 60_000  # 5 minutes — covers manual 2FA / captcha
_CHALLENGE_FIELD_TIMEOUT_MS = 3_000


async def run_login() -> None:
    """Launch headed Chromium, autofill if envs set, wait for /home, save state."""
    cfg = load_config()
    autofill = bool(cfg.x_username and cfg.x_password)
    log.info("login start autofill=%s", autofill)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            ctx = await browser.new_context()
            page = await ctx.new_page()
            await page.goto(_LOGIN_URL)

            if autofill:
                await _autofill(page, cfg.x_username, cfg.x_password)
            else:
                log.info(
                    "no credentials in env — log in manually in the browser window"
                )

            try:
                await page.wait_for_url(_HOME_URL, timeout=_LANDING_TIMEOUT_MS)
            except PlaywrightTimeoutError as exc:
                raise XAuthError(
                    "login did not complete within 5 minutes"
                ) from exc

            cfg.state_path.parent.mkdir(parents=True, exist_ok=True)
            await ctx.storage_state(path=str(cfg.state_path))
            log.info("state saved to %s", cfg.state_path)
        finally:
            await browser.close()


async def _autofill(page, username: str, password: str) -> None:
    """Best-effort autofill. If a selector misses, the user can still type
    manually in the open window — we never raise here."""
    try:
        await page.fill('input[autocomplete="username"]', username)
        await page.click('button:has-text("Next")')
    except PlaywrightTimeoutError:
        log.warning("username/Next selector missed — fill manually")
        return

    # X sometimes asks for username again on suspicious-login challenge.
    try:
        await page.wait_for_selector(
            'input[data-testid="ocfEnterTextTextInput"]',
            timeout=_CHALLENGE_FIELD_TIMEOUT_MS,
        )
        await page.fill(
            'input[data-testid="ocfEnterTextTextInput"]', username
        )
        await page.click('button:has-text("Next")')
    except PlaywrightTimeoutError:
        pass

    try:
        await page.fill('input[name="password"]', password)
        await page.click('button[data-testid="LoginForm_Login_Button"]')
    except PlaywrightTimeoutError:
        log.warning("password selector missed — fill manually")
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `.venv/bin/python -c "from xscraper.login import run_login; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add xscraper/login.py
git commit -m "feat(xscraper): add login subcommand with autofill + manual fallback"
```

---

## Task 10: CLI

**Files:**
- Create: `xscraper/cli.py`
- Create: `xscraper/tests/test_cli.py`

Two subcommands: `search` (default — bare positional query also routes here) and `login`. Plain output uses compact-formatted counts (`1.2k`, `15M`). JSON output uses `asdict` per tweet.

- [ ] **Step 1: Write failing test**

`xscraper/tests/test_cli.py`:

```python
"""CLI tests with monkeypatched search/login coroutines."""

from __future__ import annotations

import asyncio
import json

import pytest

from xscraper import cli
from xscraper.exceptions import XAuthError, XConfigError, XSchemaError, XTimeoutError
from xscraper.models import Tweet


_SAMPLE_TWEETS = [
    Tweet(
        id="1",
        text="hello world",
        created_at=1714056731,
        handle="alice",
        lang="en",
        like_count=42,
        retweet_count=7,
        reply_count=3,
        quote_count=1,
    ),
    Tweet(
        id="2",
        text="second",
        created_at=1714056800,
        handle="bob",
        lang="en",
        like_count=1500,
        retweet_count=0,
        reply_count=0,
        quote_count=0,
    ),
]


def _run(monkeypatch, args, capsys, *, tweets=None, login_called=None):
    if tweets is not None:
        async def fake_search(query, limit, *, headed):
            return tweets[:limit]

        monkeypatch.setattr(cli, "search", fake_search)
    if login_called is not None:
        async def fake_login():
            login_called.append(True)

        monkeypatch.setattr(cli, "run_login", fake_login)
    rc = cli.main(args)
    out, err = capsys.readouterr()
    return rc, out, err


def test_default_subcommand_runs_search(monkeypatch, capsys):
    rc, out, _ = _run(monkeypatch, ["macbook"], capsys, tweets=_SAMPLE_TWEETS)
    assert rc == 0
    assert "@alice" in out
    assert "@bob" in out
    assert "hello world" in out


def test_explicit_search_subcommand(monkeypatch, capsys):
    rc, out, _ = _run(
        monkeypatch, ["search", "macbook"], capsys, tweets=_SAMPLE_TWEETS
    )
    assert rc == 0
    assert "@alice" in out


def test_short_limit_alias(monkeypatch, capsys):
    rc, out, _ = _run(
        monkeypatch, ["macbook", "-l", "1"], capsys, tweets=_SAMPLE_TWEETS
    )
    assert rc == 0
    assert "@alice" in out
    assert "@bob" not in out


def test_long_limit_flag(monkeypatch, capsys):
    rc, out, _ = _run(
        monkeypatch, ["macbook", "--limit", "1"], capsys, tweets=_SAMPLE_TWEETS
    )
    assert rc == 0
    assert "@bob" not in out


def test_json_output(monkeypatch, capsys):
    rc, out, _ = _run(
        monkeypatch, ["macbook", "--json"], capsys, tweets=_SAMPLE_TWEETS
    )
    assert rc == 0
    parsed = json.loads(out)
    assert len(parsed) == 2
    assert parsed[0]["id"] == "1"
    assert parsed[0]["like_count"] == 42


def test_compact_count_formatting(monkeypatch, capsys):
    rc, out, _ = _run(monkeypatch, ["macbook"], capsys, tweets=_SAMPLE_TWEETS)
    assert "1.5k" in out  # bob's 1500 likes


def test_limit_zero_rejected_by_argparse(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["macbook", "-l", "0"])
    assert exc.value.code == 2


def test_limit_too_high_rejected_by_argparse(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["macbook", "-l", "21"])
    assert exc.value.code == 2


def test_login_subcommand_dispatches(monkeypatch, capsys):
    called: list[bool] = []
    rc, _, _ = _run(monkeypatch, ["login"], capsys, login_called=called)
    assert rc == 0
    assert called == [True]


@pytest.mark.parametrize(
    "exc_cls,expected_code",
    [
        (XAuthError, 1),
        (XSchemaError, 3),
        (XConfigError, 4),
        (XTimeoutError, 5),
    ],
)
def test_exception_to_exit_code(monkeypatch, capsys, exc_cls, expected_code):
    async def fake_search(query, limit, *, headed):
        raise exc_cls("boom")

    monkeypatch.setattr(cli, "search", fake_search)
    rc = cli.main(["macbook"])
    _, err = capsys.readouterr()
    assert rc == expected_code
    assert "boom" in err or exc_cls.__name__ in err
```

- [ ] **Step 2: Run test, verify FAIL**

Run: `.venv/bin/pytest xscraper/tests/test_cli.py -v`
Expected: `ModuleNotFoundError: No module named 'xscraper.cli'`.

- [ ] **Step 3: Implement `xscraper/cli.py`**

```python
"""argparse entry for `python -m xscraper`.

Subcommands:
  search (default — bare positional query also routes here)
  login

Exit codes (spec §7.4):
  0  success
  1  XAuthError
  2  argparse error (reserved by argparse)
  3  XSchemaError
  4  XConfigError
  5  XTimeoutError
  6  uncaught browser/transport error
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime, timezone

from xscraper.config import load_config, setup_logging
from xscraper.exceptions import (
    XAuthError,
    XConfigError,
    XError,
    XSchemaError,
    XTimeoutError,
)
from xscraper.login import run_login
from xscraper.models import Tweet
from xscraper.scraper import search

log = logging.getLogger("xscraper.cli")

_LIMIT_MIN = 1
_LIMIT_MAX = 20


def _limit_type(raw: str) -> int:
    n = int(raw)
    if n < _LIMIT_MIN or n > _LIMIT_MAX:
        raise argparse.ArgumentTypeError(
            f"limit must be between {_LIMIT_MIN} and {_LIMIT_MAX}"
        )
    return n


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="xscraper",
        description="Scrape X (Twitter) Latest search results via patchright.",
    )
    sub = parser.add_subparsers(dest="cmd")
    # NOTE: search is the default — we resolve a bare positional query in main().

    search_p = sub.add_parser("search", help="run a Latest-tab search")
    _add_search_args(search_p)

    login_p = sub.add_parser(
        "login", help="open a browser, log in once, write state.json"
    )
    login_p.add_argument(
        "--headed",
        action="store_true",
        help="(no-op — login is always headed)",
    )

    # Top-level args mirror search args so `xscraper "query"` works without
    # typing `search`.
    _add_search_args(parser)
    return parser


def _add_search_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("query", nargs="?", help="search term (quote multi-word)")
    p.add_argument(
        "-l",
        "--limit",
        type=_limit_type,
        default=_LIMIT_MAX,
        help=f"max tweets to return (1..{_LIMIT_MAX}, default {_LIMIT_MAX})",
    )
    p.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="emit JSON array instead of plain text",
    )
    p.add_argument(
        "--headed",
        action="store_true",
        help="run browser visibly (debugging)",
    )


def _compact(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M".replace(".0M", "M")
    if n >= 1_000:
        return f"{n / 1_000:.1f}k".replace(".0k", "k")
    return str(n)


def _render_plain(tweets: list[Tweet]) -> str:
    blocks = []
    for t in tweets:
        ts = datetime.fromtimestamp(t.created_at, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%MZ"
        )
        header = (
            f"@{t.handle} · {_compact(t.like_count)}❤ "
            f"{_compact(t.retweet_count)}🔁 "
            f"{_compact(t.reply_count)}💬 "
            f"{_compact(t.quote_count)}❝ · {ts}"
        )
        blocks.append(f"{header}\n{t.text}")
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def _render_json(tweets: list[Tweet]) -> str:
    return json.dumps([asdict(t) for t in tweets], indent=2)


async def _run_search(args: argparse.Namespace) -> int:
    tweets = await search(args.query, args.limit, headed=args.headed)
    out = _render_json(tweets) if args.as_json else _render_plain(tweets)
    sys.stdout.write(out)
    if not out.endswith("\n"):
        sys.stdout.write("\n")
    return 0


async def _run_login(args: argparse.Namespace) -> int:
    await run_login()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    cfg = load_config()
    setup_logging(cfg.log_format)

    # Default subcommand: bare positional query routes to search.
    if args.cmd is None:
        if args.query is None:
            parser.error("query is required (or use a subcommand)")
        coro = _run_search(args)
    elif args.cmd == "login":
        coro = _run_login(args)
    elif args.cmd == "search":
        if args.query is None:
            parser.error("query is required for search")
        coro = _run_search(args)
    else:  # pragma: no cover — argparse guards this
        parser.error(f"unknown subcommand {args.cmd!r}")

    try:
        return asyncio.run(coro)
    except XAuthError as e:
        log.error("XAuthError: %s", e)
        return 1
    except XSchemaError as e:
        log.error("XSchemaError: %s", e)
        return 3
    except XConfigError as e:
        log.error("XConfigError: %s", e)
        return 4
    except XTimeoutError as e:
        log.error("XTimeoutError: %s", e)
        return 5
    except XError as e:  # any other xscraper error
        log.error("%s: %s", type(e).__name__, e)
        return 6
    except Exception as e:
        log.error("uncaught %s: %s", type(e).__name__, e)
        return 6


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run test, verify PASS**

Run: `.venv/bin/pytest xscraper/tests/test_cli.py -v`
Expected: 13 passed (4 exit-code parametrize + 9 others).

- [ ] **Step 5: Run the whole xscraper test suite as a sanity check**

Run: `.venv/bin/pytest xscraper/tests -v`
Expected: all tests pass (exceptions: 5, models: 3, config: 4, graphql: 6, scraper: 3, cli: 13 = 34 passed).

- [ ] **Step 6: Commit**

```bash
git add xscraper/cli.py xscraper/tests/test_cli.py
git commit -m "feat(xscraper): add CLI with search and login subcommands"
```

---

## Task 11: README

**Files:**
- Create: `xscraper/README.md`

- [ ] **Step 1: Write `xscraper/README.md`**

```markdown
# xscraper

A thin X (Twitter) Latest-tab search scraper. Drives a logged-in `patchright`
Chromium, intercepts the `SearchTimeline` GraphQL response the browser fetches
for itself, parses tweets out, prints them.

Spec: [docs/superpowers/specs/2026-04-28-xscraper-playwright-design.md](../docs/superpowers/specs/2026-04-28-xscraper-playwright-design.md)

## Setup

```bash
# 1. install Python deps (project uses backend/requirements.txt as the source of truth)
.venv/bin/pip install -r backend/requirements.txt

# 2. download the patched Chromium binary (one-time, ~150MB)
.venv/bin/patchright install chromium

# 3. (optional) drop credentials into xscraper/.env so login can autofill
cp xscraper/.env.example xscraper/.env
$EDITOR xscraper/.env

# 4. log in once — opens a real browser window
.venv/bin/python -m xscraper login
# autofill runs if X_USERNAME + X_PASSWORD are set; otherwise type creds yourself
# solve any captcha / 2FA in the window; helper waits up to 5 minutes for /home
# on success: xscraper/state.json is written

# 5. run a search
.venv/bin/python -m xscraper "macbook pro"
```

## Usage

```bash
# search (default subcommand)
python -m xscraper "<query>" [-l N | --limit N] [--json] [--headed]
python -m xscraper search "<query>" [-l N | --limit N] [--json] [--headed]

# login (interactive — re-run when state expires)
python -m xscraper login
```

`--limit` defaults to 20 (single page). `-l` is the short alias.
`--json` swaps the pretty printer for a JSON array.
`--headed` runs the browser visibly (debugging).

## Capturing a fresh fixture

If `XSchemaError` fires, X changed the response shape. Capture a new
`SearchTimeline` JSON and update the parser:

1. Open `https://x.com/search?q=test&f=live` in your real browser.
2. DevTools → Network → filter "SearchTimeline".
3. Right-click the request → Copy → Copy response.
4. Save to `xscraper/tests/fixtures/search_latest.json`.
5. Update `xscraper/graphql.py` parser if the shape moved.
6. `pytest xscraper/tests/test_graphql.py` until green.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `XAuthError` exit 1 (search) | `state.json` expired | Re-run `python -m xscraper login` |
| `XSchemaError` exit 3 | X response shape changed | Capture fresh `SearchTimeline` JSON; update parser + fixture |
| `XTimeoutError` exit 5 | X is slow, stealth tripped, or patchright Chromium needs update | First retry; if persistent run `--headed` and watch |
| Login autofill silently does nothing | X form selector rotated | Type credentials manually in the open window; update `login.py` selectors |
| Login timed out (5 min) | 2FA unsolved, or `/home` URL changed | Verify post-login URL manually, update `wait_for_url` target |
```

- [ ] **Step 2: Commit**

```bash
git add xscraper/README.md
git commit -m "docs(xscraper): add README"
```

---

## Task 12: Manual end-to-end smoke

**Files:** none — this is a verification step.

This is the only "real X" check in the plan. We do it manually because (a) login is interactive and (b) the spec explicitly avoids live-network tests in CI. Replace the hand-crafted fixture with a real captured response while we're at it.

- [ ] **Step 1: Verify the venv is configured**

Run: `.venv/bin/python -c "import patchright; print(patchright.__version__)"`
Expected: a version number prints. If `ModuleNotFoundError`, repeat Task 1 Step 8.

- [ ] **Step 2: Run login**

Run: `.venv/bin/python -m xscraper login`
Expected:
- A Chromium window opens to `https://x.com/login`.
- If `xscraper/.env` has `X_USERNAME` + `X_PASSWORD`, fields autofill and submit.
- Solve any captcha / 2FA challenge by hand.
- Window navigates to `https://x.com/home`.
- Log line: `state saved to xscraper/state.json`.
- Process exits 0.
- File `xscraper/state.json` exists and is non-empty JSON.

- [ ] **Step 3: Run a real search**

Run: `.venv/bin/python -m xscraper "macbook pro" -l 5`
Expected:
- A headless Chromium spins up (no window).
- Up to 5 tweets print, each as a `@handle · counts · timestamp\ntext` block.
- Process exits 0.

- [ ] **Step 4: Capture the real response and replace the fixture**

While the search worked, run it again with `--headed` and DevTools open. Right-click the `SearchTimeline` request, copy response, paste into `xscraper/tests/fixtures/search_latest.json` (overwriting the hand-crafted version).

Then update `xscraper/tests/test_graphql.py::test_tweet_fields_populated` to assert on a real tweet's known fields (pick the first tweet from the captured JSON and copy id/handle/counts into the test).

- [ ] **Step 5: Run the test suite against the real fixture**

Run: `.venv/bin/pytest xscraper/tests -v`
Expected: all tests pass against the real fixture.

- [ ] **Step 6: Commit the real fixture**

```bash
git add xscraper/tests/fixtures/search_latest.json xscraper/tests/test_graphql.py
git commit -m "test(xscraper): replace hand-crafted fixture with real capture"
```

---

## Done criteria

- `python -m xscraper login` writes a working `state.json`.
- `python -m xscraper "<query>"` prints up to 20 tweets in pretty format.
- `python -m xscraper "<query>" --json` emits a valid JSON array.
- `python -m xscraper "<query>" -l 5` returns at most 5 tweets.
- `pytest xscraper/tests` is green.
- `xscraper/state.json` is gitignored (verify with `git check-ignore xscraper/state.json`).
