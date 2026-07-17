"""Brand knowledge-base routes.

Endpoints follow this shape (all require auth):

* `POST   /brands`                        — create a brand.
* `GET    /brands/{slug}`                 — read brand profile.
* `PATCH  /brands/{slug}`                 — update identity fields.
* `POST   /brands/{slug}/assets/text`     — ingest freeform text (JSON).
* `POST   /brands/{slug}/assets/pdf`      — upload + ingest a PDF.
* `POST   /brands/{slug}/assets/image`    — upload + ingest a reference image.
* `POST   /brands/{slug}/assets/logo`     — upload + ingest a logo image.
* `POST   /brands/{slug}/voice`           — add a do/don't pair.
* `POST   /brands/{slug}/persona`         — set / re-embed the persona.
* `POST   /brands/{slug}/competitors`     — set / re-embed the competitor list.
* `GET    /brands/{slug}/understanding`   — BrandUnderstandingScore breakdown.
* `POST   /brands/{slug}/retrieve`        — hybrid retrieval (debug + agents).
"""

from __future__ import annotations

import logging
import mimetypes
from typing import cast

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.deps import get_current_user
from backend.api.schemas import (
    BrandContextResponse,
    BrandCreateRequest,
    BrandOut,
    BrandProfileUpdate,
    BrandRetrieveRequest,
    BrandUnderstandingResponse,
    CompetitorsRequest,
    ImageHitOut,
    IngestResponse,
    PersonaRequest,
    TextHitOut,
    TextIngestRequest,
    VoicePairRequest,
)
from backend.brand import ingestion, rag, understanding
from backend.db.base import get_session
from backend.db.models import Brand, BrandAssetKind, User

router = APIRouter(prefix="/brands", tags=["brands"])
_LOG = logging.getLogger(__name__)

_MAX_PDF_BYTES = 25 * 1024 * 1024   # 25 MB
_MAX_IMAGE_BYTES = 15 * 1024 * 1024  # 15 MB
_ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


# --- Brand CRUD ----------------------------------------------------------

@router.post("", response_model=BrandOut, status_code=status.HTTP_201_CREATED)
def create_brand(
    payload: BrandCreateRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001 — auth guard
    session: Session = Depends(get_session),
) -> Brand:
    existing = session.scalar(select(Brand).where(Brand.slug == payload.slug))
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Brand '{payload.slug}' already exists",
        )
    brand = Brand(
        slug=payload.slug,
        name=payload.name,
        voice=payload.voice,
        guardrails=payload.guardrails,
    )
    session.add(brand)
    session.commit()
    session.refresh(brand)
    return brand


@router.get("/{slug}", response_model=BrandOut)
def get_brand(
    slug: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> Brand:
    return _get_brand_or_404(session, slug)


@router.patch("/{slug}", response_model=BrandOut)
def update_brand(
    slug: str,
    payload: BrandProfileUpdate,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> Brand:
    brand = _get_brand_or_404(session, slug)
    if payload.name is not None:
        brand.name = payload.name
    if payload.voice is not None:
        brand.voice = payload.voice
    if payload.guardrails is not None:
        brand.guardrails = payload.guardrails
    if payload.palette_dominant_hex is not None or payload.palette_accent_hex is not None:
        ingestion.set_palette(
            brand=brand,
            dominant_hex=payload.palette_dominant_hex,
            accent_hex=payload.palette_accent_hex,
        )
    if payload.typography is not None:
        ingestion.set_typography(brand=brand, typography=payload.typography)
    session.commit()
    session.refresh(brand)
    return brand


# --- Ingestion -----------------------------------------------------------

@router.post("/{slug}/assets/text", response_model=IngestResponse)
async def ingest_text_route(
    slug: str,
    payload: TextIngestRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> IngestResponse:
    brand = _get_brand_or_404(session, slug)
    result = await ingestion.ingest_text(
        brand=brand, text=payload.text, source=payload.source, session=session,
    )
    session.commit()
    return IngestResponse(
        asset_id=result.asset_id,
        text_chunks=result.text_chunks,
        image_chunks=result.image_chunks,
    )


@router.post("/{slug}/assets/pdf", response_model=IngestResponse)
async def ingest_pdf_route(
    slug: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> IngestResponse:
    brand = _get_brand_or_404(session, slug)
    payload = await _read_upload(file, max_bytes=_MAX_PDF_BYTES, expect="application/pdf")
    source_name = file.filename or "upload.pdf"
    result = await ingestion.ingest_pdf(
        brand=brand, pdf_bytes=payload, source_name=source_name, session=session,
    )
    session.commit()
    return IngestResponse(
        asset_id=result.asset_id,
        text_chunks=result.text_chunks,
        image_chunks=result.image_chunks,
    )


@router.post("/{slug}/assets/image", response_model=IngestResponse)
async def ingest_image_route(
    slug: str,
    file: UploadFile = File(...),
    caption: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> IngestResponse:
    brand = _get_brand_or_404(session, slug)
    image_bytes = await _read_image_upload(file)
    result = ingestion.ingest_image(
        brand=brand,
        image_bytes=image_bytes,
        source_name=file.filename or "image",
        session=session,
        caption=caption,
        kind=BrandAssetKind.IMAGE,
    )
    session.commit()
    return IngestResponse(
        asset_id=result.asset_id,
        text_chunks=result.text_chunks,
        image_chunks=result.image_chunks,
    )


@router.post("/{slug}/assets/logo", response_model=IngestResponse)
async def ingest_logo_route(
    slug: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> IngestResponse:
    brand = _get_brand_or_404(session, slug)
    image_bytes = await _read_image_upload(file)
    result = ingestion.ingest_image(
        brand=brand,
        image_bytes=image_bytes,
        source_name=file.filename or "logo",
        session=session,
        caption="brand logo",
        kind=BrandAssetKind.LOGO,
    )
    session.commit()
    return IngestResponse(
        asset_id=result.asset_id,
        text_chunks=result.text_chunks,
        image_chunks=result.image_chunks,
    )


@router.post("/{slug}/voice", response_model=IngestResponse)
async def add_voice_pair(
    slug: str,
    payload: VoicePairRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> IngestResponse:
    brand = _get_brand_or_404(session, slug)
    result = await ingestion.ingest_voice_pair(
        brand=brand, do=payload.do, dont=payload.dont, session=session,
    )
    session.commit()
    return IngestResponse(
        asset_id=result.asset_id,
        text_chunks=result.text_chunks,
        image_chunks=result.image_chunks,
    )


@router.post("/{slug}/persona", response_model=BrandOut)
async def set_persona(
    slug: str,
    payload: PersonaRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> Brand:
    brand = _get_brand_or_404(session, slug)
    await ingestion.set_persona(brand=brand, persona=payload.persona, session=session)
    session.commit()
    session.refresh(brand)
    return brand


@router.post("/{slug}/competitors", response_model=BrandOut)
async def set_competitors(
    slug: str,
    payload: CompetitorsRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> Brand:
    brand = _get_brand_or_404(session, slug)
    await ingestion.set_competitors(
        brand=brand, competitors=payload.competitors, session=session,
    )
    session.commit()
    session.refresh(brand)
    return brand


# --- Understanding + retrieval ------------------------------------------

@router.get("/{slug}/understanding", response_model=BrandUnderstandingResponse)
def get_understanding(
    slug: str,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> BrandUnderstandingResponse:
    brand = _get_brand_or_404(session, slug)
    breakdown = understanding.compute_understanding(brand, session)
    return BrandUnderstandingResponse(score=breakdown.total, breakdown=breakdown.as_dict())


@router.post("/{slug}/retrieve", response_model=BrandContextResponse)
async def retrieve(
    slug: str,
    payload: BrandRetrieveRequest,
    current_user: User = Depends(get_current_user),  # noqa: ARG001
    session: Session = Depends(get_session),
) -> BrandContextResponse:
    brand = _get_brand_or_404(session, slug)
    ctx = await rag.retrieve_brand_context(
        brand=brand,
        query=payload.query,
        session=session,
        scene_palette=payload.scene_palette,
        text_k=payload.text_k,
        voice_k=payload.voice_k,
        image_k=payload.image_k,
    )
    return BrandContextResponse(
        text_snippets=[_text_hit_out(h) for h in ctx.text_snippets],
        voice_dos=[_text_hit_out(h) for h in ctx.voice_dos],
        voice_donts=[_text_hit_out(h) for h in ctx.voice_donts],
        reference_images=[_image_hit_out(h) for h in ctx.reference_images],
        palette_hints=ctx.palette_hints,
    )


# --- Helpers -------------------------------------------------------------

def _get_brand_or_404(session: Session, slug: str) -> Brand:
    brand = session.scalar(select(Brand).where(Brand.slug == slug))
    if brand is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Brand '{slug}' not found"
        )
    return brand


async def _read_upload(file: UploadFile, *, max_bytes: int, expect: str | None = None) -> bytes:
    payload = await file.read()
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty upload"
        )
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload exceeds {max_bytes} bytes",
        )
    if expect is not None:
        media_type = _resolve_media_type(file)
        if media_type != expect:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Expected {expect}, got {media_type}",
            )
    return payload


async def _read_image_upload(file: UploadFile) -> bytes:
    payload = await _read_upload(file, max_bytes=_MAX_IMAGE_BYTES)
    media_type = _resolve_media_type(file)
    if media_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported image type: {media_type}",
        )
    return payload


def _resolve_media_type(file: UploadFile) -> str:
    if file.content_type and file.content_type != "application/octet-stream":
        return file.content_type
    if file.filename:
        guessed, _ = mimetypes.guess_type(file.filename)
        if guessed:
            return guessed
    return "application/octet-stream"


def _text_hit_out(hit: rag.TextHit) -> TextHitOut:
    return TextHitOut(
        chunk_id=hit.chunk_id,
        text=hit.text,
        source=hit.source,
        kind=hit.kind.value,
        score=hit.score,
        meta=cast(dict, hit.meta) if hit.meta else None,
    )


def _image_hit_out(hit: rag.ImageHit) -> ImageHitOut:
    return ImageHitOut(
        chunk_id=hit.chunk_id,
        image_path=hit.image_path,
        caption=hit.caption,
        palette_hex=hit.palette_hex,
        score=hit.score,
        meta=cast(dict, hit.meta) if hit.meta else None,
    )
