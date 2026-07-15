"""Procrastinate app singleton.

Procrastinate stores its queue in the same Postgres instance as the app data
(one less service to run). Tasks are registered in sibling modules by
decorating with `@app.task(...)`.
"""

from __future__ import annotations

import asyncio
import sys

from procrastinate import App, PsycopgConnector

from backend.config import get_settings

# psycopg's async driver requires SelectorEventLoop; asyncio on Windows
# defaults to ProactorEventLoop which raises "cannot use ProactorEventLoop".
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


def _libpq_dsn(sqlalchemy_url: str) -> str:
    """Strip SQLAlchemy driver suffix (`+psycopg`, `+asyncpg`, …) for raw libpq.

    Procrastinate's `PsycopgConnector` speaks libpq directly and rejects the
    SQLAlchemy-flavoured URL scheme.
    """
    if sqlalchemy_url.startswith("postgresql+"):
        _, _, tail = sqlalchemy_url.partition("+")
        # `psycopg://user:pw@...` → `postgresql://user:pw@...`
        _, _, remainder = tail.partition("://")
        return f"postgresql://{remainder}"
    return sqlalchemy_url


def _build_app() -> App:
    settings = get_settings()
    connector = PsycopgConnector(conninfo=_libpq_dsn(settings.database_url))
    return App(connector=connector, import_paths=["backend.workers.tasks"])


app: App = _build_app()
