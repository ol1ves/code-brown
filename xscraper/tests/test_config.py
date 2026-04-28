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
