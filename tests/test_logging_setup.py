"""Logging configuration: JSON formatter by default, key=value via
LOG_FORMAT=text. Both formatters merge any ``extra`` fields onto the line.
"""

from __future__ import annotations

import io
import json
import logging

from backend.logging_setup import (
    JsonFormatter,
    KeyValueFormatter,
    configure_logging,
)


def _emit_with_formatter(formatter: logging.Formatter, *, extra: dict) -> str:
    logger = logging.getLogger("test.logging_setup")
    logger.handlers.clear()
    logger.propagate = False
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("hello", extra=extra)
    return buf.getvalue().strip()


def test_json_formatter_emits_required_fields():
    line = _emit_with_formatter(JsonFormatter(), extra={"run_id": "abc", "stage": "scrape"})
    payload = json.loads(line)
    assert payload["msg"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "test.logging_setup"
    assert payload["run_id"] == "abc"
    assert payload["stage"] == "scrape"
    assert "ts" in payload


def test_key_value_formatter_includes_extras_and_msg():
    line = _emit_with_formatter(KeyValueFormatter(), extra={"run_id": "abc", "duration_ms": 42})
    assert "run_id=abc" in line
    assert "duration_ms=42" in line
    assert "INFO" in line
    assert "hello" in line


def test_configure_logging_defaults_to_json(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    configure_logging(level="INFO")
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, JsonFormatter)


def test_configure_logging_text_override(monkeypatch):
    monkeypatch.setenv("LOG_FORMAT", "text")
    configure_logging(level="INFO")
    handlers = logging.getLogger().handlers
    assert len(handlers) == 1
    assert isinstance(handlers[0].formatter, KeyValueFormatter)


def test_configure_logging_clears_existing_handlers(monkeypatch):
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    root = logging.getLogger()
    root.addHandler(logging.NullHandler())
    root.addHandler(logging.NullHandler())
    configure_logging(level="DEBUG")
    assert len(root.handlers) == 1
