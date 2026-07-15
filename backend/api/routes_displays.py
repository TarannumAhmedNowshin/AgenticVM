"""Display upload + analysis routes.

`POST /displays/analyze` — accepts a display photo + brand slug, persists the
image, creates a pending `Analysis`, and enqueues the perception task.

`GET /analyses/{id}` — poll for status + scene graph.
"""

from __future__ import annotations

import hashlib
import logging
import mimetypes
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user
from backend.api.schemas import AnalysisOut, AnalyzeResponse, DisplayOut
from backend.config import get_settings
from backend.db.base import get_session
from backend.db.models import Analysis, AnalysisStatus, Brand, Display, User

router = APIRouter(tags=["displays"])
_LOG = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15 MB
_ALLOWED_MEDIA_TYPES = {"image/jpeg", "image/png", "image/webp"}


@router.post(
    "/displays/analyze",
    response_model=AnalyzeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def analyze_display(
    brand_slug: str = Form(...),
    image: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> AnalyzeResponse:
    """Upload a display photo and enqueue perception. Returns 202 with IDs to poll."""
    brand = session.scalar(select(Brand).where(Brand.slug == brand_slug))
    if brand is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Brand '{brand_slug}' not found",
        )

    media_type = _normalise_media_type(image.content_type, image.filename)
    if media_type not in _ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported media type: {media_type}",
        )

    image_bytes = await image.read()
    if not image_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty image upload"
        )
    if len(image_bytes) > _MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Image exceeds {_MAX_UPLOAD_BYTES} bytes",
        )

    width, height = _dimensions(image_bytes)
    if width is None or height is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is not a decodable image",
        )

    sha256 = hashlib.sha256(image_bytes).hexdigest()
    image_path = _persist_image(image_bytes, brand.slug, sha256, media_type)

    display = Display(
        brand_id=brand.id,
        user_id=current_user.id,
        image_path=str(image_path),
        image_sha256=sha256,
        media_type=media_type,
        width_px=width,
        height_px=height,
    )
    session.add(display)
    session.flush()

    analysis = Analysis(display_id=display.id, status=AnalysisStatus.PENDING)
    session.add(analysis)
    session.commit()
    session.refresh(display)
    session.refresh(analysis)

    await _enqueue_perception(analysis.id)

    return AnalyzeResponse(
        display=DisplayOut.model_validate(display),
        analysis=AnalysisOut.model_validate(analysis),
    )


@router.get("/analyses/{analysis_id}", response_model=AnalysisOut)
def get_analysis(
    analysis_id: int,
    current_user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> Analysis:
    analysis = session.get(Analysis, analysis_id)
    if analysis is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    display = session.get(Display, analysis.display_id)
    if display is None or display.user_id != current_user.id:
        # Don't leak the existence of other users' analyses.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Analysis not found")

    return analysis


# --- helpers -------------------------------------------------------------

def _normalise_media_type(content_type: str | None, filename: str | None) -> str:
    if content_type and content_type != "application/octet-stream":
        return content_type
    if filename:
        guessed, _ = mimetypes.guess_type(filename)
        if guessed:
            return guessed
    return "application/octet-stream"


def _dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            img.verify()
        with Image.open(BytesIO(image_bytes)) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001
        return None, None


def _persist_image(image_bytes: bytes, brand_slug: str, sha256: str, media_type: str) -> Path:
    settings = get_settings()
    ext = mimetypes.guess_extension(media_type) or ".bin"
    # Store as `<storage_dir>/displays/<brand_slug>/<sha256>-<uuid><ext>`.
    # sha256 dedupes semantically; the uuid segment prevents accidental collision
    # if the same image is uploaded twice with different metadata.
    subdir = settings.storage_dir / "displays" / brand_slug
    subdir.mkdir(parents=True, exist_ok=True)
    name = f"{sha256[:16]}-{uuid.uuid4().hex[:8]}{ext}"
    path = subdir / name
    path.write_bytes(image_bytes)
    return path


async def _enqueue_perception(analysis_id: int) -> None:
    """Enqueue the perception job.

    Failure to enqueue does NOT roll back the Analysis row — the row will
    stay `pending` and can be retried manually. We surface the error via
    logs rather than 500ing the upload.
    """
    try:
        # Imported lazily so a misconfigured procrastinate connector doesn't
        # break unrelated routes at import time.
        from backend.workers.tasks import run_perception

        await run_perception.defer_async(analysis_id=analysis_id)
    except Exception as exc:  # noqa: BLE001
        _LOG.exception("Failed to enqueue perception for analysis %s: %s", analysis_id, exc)
