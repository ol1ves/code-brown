"""Config loader unit tests."""

from __future__ import annotations

import logging

import pytest

from xscraper.config import (
    DEFAULT_BEARER,
    DEFAULT_USER_AGENT,
    Config,
    load_config,
)
from xscraper.exceptions import XConfigError


def test_load_config_required_vars(monkeypatch):
    monkeypatch.setenv("X_AUTH_TOKEN", "tok")
    monkeypatch.setenv("X_CT0", "csrf")
    monkeypatch.delenv("X_BEARER", raising=False)
    cfg = load_config()
    assert isinstance(cfg, Config)
    assert cfg.auth_token == "tok"
    assert cfg.ct0 == "csrf"
    assert cfg.bearer == DEFAULT_BEARER
    assert cfg.user_agent == DEFAULT_USER_AGENT


def test_load_config_missing_auth_token_raises(monkeypatch):
    monkeypatch.delenv("X_AUTH_TOKEN", raising=False)
    monkeypatch.setenv("X_CT0", "csrf")
    with pytest.raises(XConfigError, match="X_AUTH_TOKEN"):
        load_config()


def test_load_config_missing_ct0_raises(monkeypatch):
    monkeypatch.setenv("X_AUTH_TOKEN", "tok")
    monkeypatch.delenv("X_CT0", raising=False)
    with pytest.raises(XConfigError, match="X_CT0"):
        load_config()


def test_load_config_logs_when_bearer_defaulted(monkeypatch, caplog):
    monkeypatch.setenv("X_AUTH_TOKEN", "tok")
    monkeypatch.setenv("X_CT0", "csrf")
    monkeypatch.delenv("X_BEARER", raising=False)
    with caplog.at_level(logging.INFO, logger="xscraper.config"):
        load_config()
    messages = [r.getMessage() for r in caplog.records if r.name == "xscraper.config"]
    assert any("X_BEARER not set" in m for m in messages)


def test_load_config_does_not_log_when_bearer_set(monkeypatch, caplog):
    monkeypatch.setenv("X_AUTH_TOKEN", "tok")
    monkeypatch.setenv("X_CT0", "csrf")
    monkeypatch.setenv("X_BEARER", "custom-bearer")
    with caplog.at_level(logging.INFO, logger="xscraper.config"):
        cfg = load_config()
    assert cfg.bearer == "custom-bearer"
    messages = [r.getMessage() for r in caplog.records if r.name == "xscraper.config"]
    assert not any("X_BEARER" in m for m in messages)
