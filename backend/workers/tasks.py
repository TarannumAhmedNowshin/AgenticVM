"""Registered background tasks.

Discovered by procrastinate via `import_paths=["backend.workers.tasks"]` in
`backend.workers.app`.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from backend.agents.perception.perception import perceive
from backend.brand.product_matcher import match_scene_products
from backend.db.base import SessionLocal
from backend.db.models import Analysis, AnalysisStatus, Display
from backend.workers.app import app

_LOG = logging.getLogger(__name__)


@app.task(name="avms.ping", queue="default")
async def ping(message: str = "pong") -> str:  # pragma: no cover - trivial
    return message


@app.task(name="avms.run_perception", queue="perception")
async def run_perception(analysis_id: int) -> None:
    """Task wrapper — see `_run_perception` for the actual logic."""
    await _run_perception(analysis_id)


async def _run_perception(analysis_id: int) -> None:
    """Load a pending Analysis, run perception + product matching, persist.

    On failure the Analysis row is flipped to `failed` with the error message
    recorded — the exception is re-raised so procrastinate marks the job as
    failed too.
    """
    display_ctx = _mark_running(analysis_id)
    if display_ctx is None:
        _LOG.warning("Analysis %s not found or already terminal", analysis_id)
        return

    display_id, image_path, media_type, brand_id = display_ctx

    try:
        image_bytes = Path(image_path).read_bytes()
        scene = await perceive(
            image_bytes,
            image_id=f"display-{display_id}",
            media_type=media_type,
        )
        with SessionLocal() as session:
            match_scene_products(
                scene,
                image_bytes,
                brand_id=brand_id,
                session=session,
            )
        _persist_success(analysis_id, scene)
    except Exception as exc:  # noqa: BLE001
        _persist_failure(analysis_id, exc)
        raise


def _mark_running(analysis_id: int) -> tuple[int, str, str, int] | None:
    with SessionLocal() as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None or analysis.status not in {
            AnalysisStatus.PENDING,
            AnalysisStatus.FAILED,
        }:
            return None
        display = session.get(Display, analysis.display_id)
        if display is None:
            analysis.status = AnalysisStatus.FAILED
            analysis.error = "Owning display was deleted"
            session.commit()
            return None
        analysis.status = AnalysisStatus.RUNNING
        analysis.error = None
        session.commit()
        return display.id, display.image_path, display.media_type, display.brand_id


def _persist_success(analysis_id: int, scene) -> None:  # type: ignore[no-untyped-def]
    with SessionLocal() as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return
        analysis.status = AnalysisStatus.COMPLETE
        analysis.scene_graph = scene.model_dump(mode="json")
        analysis.prompt_version = scene.prompt_version
        analysis.model_id = scene.model_id
        analysis.error = None
        session.commit()


def _persist_failure(analysis_id: int, exc: BaseException) -> None:
    with SessionLocal() as session:
        analysis = session.get(Analysis, analysis_id)
        if analysis is None:
            return
        analysis.status = AnalysisStatus.FAILED
        analysis.error = f"{type(exc).__name__}: {exc}"[:2000]
        session.commit()


def run_perception_sync(analysis_id: int) -> None:
    """Sync entry point for tests / local runs without procrastinate."""
    asyncio.run(_run_perception(analysis_id))
