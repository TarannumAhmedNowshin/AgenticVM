"""Tests for the display upload + analysis polling routes.

Requires the local Postgres from `docker-compose.yml` to be up and Alembic
to be at head. Uses the demo brand seeded by `backend/scripts/seed_demo_brand.py`
(seeding is idempotent and re-run at the top of this module).
"""

from __future__ import annotations

import time
from io import BytesIO

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from backend.api import routes_displays
from backend.db.base import SessionLocal
from backend.db.models import Analysis, AnalysisStatus, Brand, Display
from backend.scripts import seed_demo_brand


@pytest.fixture(scope="module", autouse=True)
def _seed_brand() -> None:
    """Ensure the demo brand row exists (products optional)."""
    with SessionLocal() as session:
        if session.scalar(select(Brand).where(Brand.slug == seed_demo_brand.DEMO_BRAND_SLUG)):
            return
    seed_demo_brand.main()


def _register_and_login(client: TestClient) -> str:
    email = f"displays-{int(time.time() * 1000)}@example.com"
    password = "correcthorsebattery"
    r = client.post("/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    r = client.post("/auth/login", data={"username": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def _jpeg_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (128, 96), (180, 200, 220)).save(buffer, format="JPEG")
    return buffer.getvalue()


@pytest.fixture(autouse=True)
def _stub_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    """Skip real procrastinate enqueue — the point is to exercise the route."""

    async def _noop(analysis_id: int) -> None:
        return None

    monkeypatch.setattr(routes_displays, "_enqueue_perception", _noop)


def test_analyze_display_creates_pending_analysis(client: TestClient) -> None:
    token = _register_and_login(client)
    response = client.post(
        "/displays/analyze",
        headers={"Authorization": f"Bearer {token}"},
        data={"brand_slug": seed_demo_brand.DEMO_BRAND_SLUG},
        files={"image": ("display.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["display"]["media_type"] == "image/jpeg"
    assert body["display"]["width_px"] == 128
    assert body["display"]["height_px"] == 96
    assert body["analysis"]["status"] == AnalysisStatus.PENDING.value

    with SessionLocal() as session:
        analysis = session.get(Analysis, body["analysis"]["id"])
        assert analysis is not None
        assert analysis.status == AnalysisStatus.PENDING
        display = session.get(Display, analysis.display_id)
        assert display is not None
        assert display.image_sha256 and len(display.image_sha256) == 64


def test_analyze_display_rejects_unknown_brand(client: TestClient) -> None:
    token = _register_and_login(client)
    response = client.post(
        "/displays/analyze",
        headers={"Authorization": f"Bearer {token}"},
        data={"brand_slug": "does-not-exist"},
        files={"image": ("display.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 404


def test_analyze_display_requires_auth(client: TestClient) -> None:
    response = client.post(
        "/displays/analyze",
        data={"brand_slug": seed_demo_brand.DEMO_BRAND_SLUG},
        files={"image": ("display.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    assert response.status_code == 401


def test_analyze_display_rejects_non_image(client: TestClient) -> None:
    token = _register_and_login(client)
    response = client.post(
        "/displays/analyze",
        headers={"Authorization": f"Bearer {token}"},
        data={"brand_slug": seed_demo_brand.DEMO_BRAND_SLUG},
        files={"image": ("hello.txt", b"not an image", "text/plain")},
    )
    assert response.status_code == 415


def test_get_analysis_scopes_to_owner(client: TestClient) -> None:
    token_a = _register_and_login(client)
    r = client.post(
        "/displays/analyze",
        headers={"Authorization": f"Bearer {token_a}"},
        data={"brand_slug": seed_demo_brand.DEMO_BRAND_SLUG},
        files={"image": ("display.jpg", _jpeg_bytes(), "image/jpeg")},
    )
    analysis_id = r.json()["analysis"]["id"]

    # Same user can read.
    r = client.get(f"/analyses/{analysis_id}", headers={"Authorization": f"Bearer {token_a}"})
    assert r.status_code == 200
    assert r.json()["id"] == analysis_id

    # A different user cannot.
    token_b = _register_and_login(client)
    r = client.get(f"/analyses/{analysis_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert r.status_code == 404
