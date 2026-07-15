"""Tests for the perception worker task.

Uses in-DB `Display` / `Analysis` rows but mocks the Claude vision + CLIP
matcher calls so the test is fully offline.
"""

from __future__ import annotations

import time
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

from backend.agents.perception.scene_graph import (
    BoundingBox,
    DetectedProduct,
    ScenePalette,
    SceneGraph,
    SceneZones,
)
from backend.db.base import SessionLocal
from backend.db.models import Analysis, AnalysisStatus, Brand, Display, User
from backend.scripts import seed_demo_brand
from backend.workers import tasks


def _write_display(tmp_path: Path, brand_id: int, user_id: int) -> tuple[Display, bytes]:
    buffer = BytesIO()
    Image.new("RGB", (64, 48), (200, 150, 100)).save(buffer, format="JPEG")
    image_bytes = buffer.getvalue()
    image_path = tmp_path / "display.jpg"
    image_path.write_bytes(image_bytes)

    with SessionLocal() as session:
        display = Display(
            brand_id=brand_id,
            user_id=user_id,
            image_path=str(image_path),
            image_sha256="a" * 64,
            media_type="image/jpeg",
            width_px=64,
            height_px=48,
        )
        session.add(display)
        session.flush()
        analysis = Analysis(display_id=display.id, status=AnalysisStatus.PENDING)
        session.add(analysis)
        session.commit()
        session.refresh(display)
        session.refresh(analysis)
        return display, image_bytes


def _ensure_demo_brand_and_user() -> tuple[int, int]:
    with SessionLocal() as session:
        brand = session.scalar(select(Brand).where(Brand.slug == seed_demo_brand.DEMO_BRAND_SLUG))
    if brand is None:
        seed_demo_brand.main()
        with SessionLocal() as session:
            brand = session.scalar(
                select(Brand).where(Brand.slug == seed_demo_brand.DEMO_BRAND_SLUG)
            )
    assert brand is not None
    with SessionLocal() as session:
        email = f"worker-{int(time.time() * 1000)}@example.com"
        user = User(email=email, hashed_password="x", is_active=True)
        session.add(user)
        session.commit()
        session.refresh(user)
        return brand.id, user.id


def _fake_scene_graph(image_id: str) -> SceneGraph:
    return SceneGraph(
        image_id=image_id,
        products=[
            DetectedProduct(
                label="mug",
                bbox=BoundingBox(x=0.1, y=0.1, w=0.4, h=0.4),
                category="home/kitchen",
            )
        ],
        text=[],
        palette=ScenePalette(dominant_hex=["#123456"], accent_hex=[]),
        zones=SceneZones(focal_points=[]),
        lighting_notes="warm",
        composition_notes="centred",
        prompt_version="test-version",
        model_id="test-model",
    )


async def test_run_perception_marks_analysis_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand_id, user_id = _ensure_demo_brand_and_user()
    display, _ = _write_display(tmp_path, brand_id=brand_id, user_id=user_id)

    with SessionLocal() as session:
        analysis_id = session.scalar(
            select(Analysis.id).where(Analysis.display_id == display.id)
        )
    assert analysis_id is not None

    async def _fake_perceive(image_bytes: bytes, *, image_id: str, media_type: str) -> SceneGraph:
        return _fake_scene_graph(image_id)

    def _fake_match(scene, image_bytes, *, brand_id, session):  # noqa: ANN001, ARG001
        return scene

    monkeypatch.setattr(tasks, "perceive", _fake_perceive)
    monkeypatch.setattr(tasks, "match_scene_products", _fake_match)

    await tasks._run_perception(analysis_id)

    with SessionLocal() as session:
        analysis = session.get(Analysis, analysis_id)
        assert analysis is not None
        assert analysis.status == AnalysisStatus.COMPLETE
        assert analysis.scene_graph is not None
        assert analysis.scene_graph["products"][0]["label"] == "mug"
        assert analysis.prompt_version == "test-version"
        assert analysis.model_id == "test-model"
        assert analysis.error is None


async def test_run_perception_records_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    brand_id, user_id = _ensure_demo_brand_and_user()
    display, _ = _write_display(tmp_path, brand_id=brand_id, user_id=user_id)

    with SessionLocal() as session:
        analysis_id = session.scalar(
            select(Analysis.id).where(Analysis.display_id == display.id)
        )
    assert analysis_id is not None

    async def _boom(*args, **kwargs):  # noqa: ANN002, ANN003
        raise RuntimeError("perception broke")

    monkeypatch.setattr(tasks, "perceive", _boom)

    with pytest.raises(RuntimeError):
        await tasks._run_perception(analysis_id)

    with SessionLocal() as session:
        analysis = session.get(Analysis, analysis_id)
        assert analysis is not None
        assert analysis.status == AnalysisStatus.FAILED
        assert analysis.error and "perception broke" in analysis.error
