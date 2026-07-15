"""Shared pytest fixtures.

Uses an in-process TestClient against the FastAPI app. Assumes a running
Postgres (docker compose up -d) with the current Alembic head applied.
For unit tests that don't need the DB, prefer building minimal fixtures.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from backend.api.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:
        yield c
