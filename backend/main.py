"""FastAPI app.

Public route: ``/health``.
Authenticated routes: ``/search`` and ``/recommendations``.
"""

from __future__ import annotations

import os
import secrets
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.responses import Response
from supabase import create_client

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

load_dotenv()

from backend.logging_setup import configure_logging
from backend.pipeline.context import RunContext
from backend.pipeline.search import run_search
from ev.ev import set_store as set_ev_store
from scraper.scraper import set_store as set_scraper_store
from shared.models import (
    Recommendation,
    SearchParams,
    SearchResponse,
)
from shared.store import (
    ListingStore,
    get_recommendations_store,
    set_recommendations_store,
)

API_KEY = os.environ.get("API_KEY", "").strip()


def _is_public_path(path: str) -> bool:
    return path == "/health" or path.rstrip("/") == "/health"


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(level=os.environ.get("LOG_LEVEL", "INFO"))
    if not API_KEY:
        raise RuntimeError("API_KEY environment variable must be set and non-empty")
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    service_role = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not supabase_url or not service_role:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set and non-empty"
        )
    client = create_client(supabase_url, service_role)
    store = ListingStore(client)
    app.state.store = store
    set_scraper_store(store)
    set_ev_store(store)
    set_recommendations_store(store)
    yield


app = FastAPI(
    title="code-brown backend",
    lifespan=lifespan,
)


@app.middleware("http")
async def bearer_auth_middleware(request: Request, call_next):
    if _is_public_path(request.url.path):
        return await call_next(request)

    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    token = auth.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(token, API_KEY):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized"})
    return await call_next(request)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.head("/health")
def health_head():
    return Response(status_code=200)


class RecommendationsResponse(BaseModel):
    items: list[Recommendation] = Field(default_factory=list)


@app.post("/search", response_model=SearchResponse)
async def search(params: SearchParams) -> SearchResponse:
    ctx = RunContext()
    return await run_search(params, ctx)


@app.get("/recommendations", response_model=RecommendationsResponse)
def recommendations(
    limit: int = Query(default=50, ge=1, le=200),
) -> RecommendationsResponse:
    store = get_recommendations_store()
    if store is None:
        return RecommendationsResponse(items=[])
    rows = store.list_recommendations(limit=limit)
    items = [Recommendation.model_validate(r) for r in rows]
    return RecommendationsResponse(items=items)
