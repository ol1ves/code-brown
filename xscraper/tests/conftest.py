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
