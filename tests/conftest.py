"""Shared fixtures for top-level tests/.

The ``ListingStore`` accessor in ``shared.store`` is a process-global. Tests
that wire a real Supabase client (via ``backend.cli._wire_stores`` or the
FastAPI lifespan) leave that global set on completion, which would cause
unrelated downstream tests to attempt real DB writes through the
orchestrator's persist path. Reset before each test to keep state hermetic.
"""

from __future__ import annotations

import pytest

from shared import store as store_mod


@pytest.fixture(autouse=True)
def _reset_recommendations_store():
    store_mod.set_recommendations_store(None)
    yield
    store_mod.set_recommendations_store(None)
