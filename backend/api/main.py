"""FastAPI application entry point.

Run locally with:
    uvicorn backend.api.main:app --reload
"""

from __future__ import annotations

import asyncio
import logging
import sys

# psycopg async (used by procrastinate) requires SelectorEventLoop; Windows
# defaults to ProactorEventLoop and refuses to connect. Must be set before
# uvicorn instantiates the loop.
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes_auth import router as auth_router
from backend.api.routes_displays import router as displays_router
from backend.config import get_settings
from backend.workers.app import app as procrastinate_app

settings = get_settings()

logging.basicConfig(level=settings.log_level)


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Open the procrastinate app so route handlers can `defer_async` jobs.
    async with procrastinate_app.open_async():
        yield


app = FastAPI(
    title="AVMS API",
    version="0.1.0",
    description="Agentic Visual Merchandising Studio — backend API.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(displays_router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "env": settings.app_env}
