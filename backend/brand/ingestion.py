"""Brand knowledge ingestion.

Turns raw brand assets — PDFs, images, palettes, voice pairs, freeform text —
into rows in `brand_assets`, `brand_text_chunks`, and `brand_image_chunks`
so `BrandRAG` can retrieve them at analysis time.

All functions here are synchronous SQLAlchemy calls except the two that need
Azure text embeddings (`ingest_text`, `ingest_pdf`, `ingest_voice_pair`) —
they take an `async` route because `AzureEmbeddingProvider` is async.

Ingestion is idempotent per (brand, sha256, source) — re-ingesting the same
asset replaces its derived chunks rather than duplicating them.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.config import get_settings
from backend.db.models import (
    Brand,
    BrandAsset,
    BrandAssetKind,
    BrandImageChunk,
    BrandTextChunk,
    BrandTextKind,
)
from backend.model_router.router import get_router

_LOG = logging.getLogger(__name__)

# --- Chunking ------------------------------------------------------------

# Aim for ~500 characters per chunk with 80 char overlap. This keeps chunks
# under the Azure embedding token cap by a wide margin (8191 tokens ≈ 30k
# chars) while still landing enough context per chunk for retrieval to be
# meaningful.
_CHUNK_TARGET_CHARS = 500
_CHUNK_OVERLAP_CHARS = 80
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def chunk_text(text: str, *, target_chars: int = _CHUNK_TARGET_CHARS,
               overlap_chars: int = _CHUNK_OVERLAP_CHARS) -> list[str]:
    """Split `text` into sentence-aware chunks of roughly `target_chars`.

    - Whitespace is collapsed inside each chunk.
    - Chunks overlap by ~`overlap_chars` so a match spanning a boundary is
      still retrievable.
    - Empty input returns an empty list.
    """
    cleaned = " ".join(text.split())
    if not cleaned:
        return []
    if len(cleaned) <= target_chars:
        return [cleaned]

    sentences = _SENTENCE_SPLIT.split(cleaned)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        # Sentences longer than the target are hard-split.
        if len(sentence) > target_chars:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(sentence), target_chars):
                chunks.append(sentence[start:start + target_chars])
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > target_chars and current:
            chunks.append(current)
            # Overlap by preserving the tail of the previous chunk.
            tail = current[-overlap_chars:] if overlap_chars else ""
            current = f"{tail} {sentence}".strip() if tail else sentence
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


# --- PDF extraction ------------------------------------------------------

def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Best-effort text extraction from a PDF byte string.

    Returns a single string joined page-by-page. Any page whose extraction
    fails is skipped with a warning rather than aborting the whole PDF.
    """
    # Deferred import so unit tests that don't touch PDFs don't pay the cost.
    from pypdf import PdfReader  # type: ignore[import-not-found]

    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    for i, page in enumerate(reader.pages):
        try:
            parts.append(page.extract_text() or "")
        except Exception as exc:  # noqa: BLE001
            _LOG.warning("Skipping PDF page %s: %s", i, exc)
    return "\n\n".join(p for p in parts if p.strip())


# --- Asset persistence ---------------------------------------------------

@dataclass(frozen=True)
class IngestResult:
    """Summary of a single ingest call."""

    asset_id: int
    text_chunks: int = 0
    image_chunks: int = 0


def _brand_asset_dir(brand_slug: str, subdir: str) -> Path:
    settings = get_settings()
    path = settings.storage_dir / "brands" / brand_slug / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def _persist_bytes(image_bytes: bytes, brand_slug: str, subdir: str,
                   sha256: str, ext: str) -> Path:
    directory = _brand_asset_dir(brand_slug, subdir)
    path = directory / f"{sha256[:16]}{ext}"
    if not path.exists():
        path.write_bytes(image_bytes)
    return path


def _upsert_asset(
    session: Session,
    *,
    brand_id: int,
    kind: BrandAssetKind,
    source_name: str,
    file_path: str | None,
    media_type: str | None,
    sha256: str | None,
    meta: dict | None = None,
) -> BrandAsset:
    """Insert or replace a `BrandAsset`. If (brand_id, sha256) already exists,
    the existing row is returned and its derived chunks are deleted so the
    caller can re-populate them cleanly."""
    if sha256:
        existing = session.scalar(
            select(BrandAsset).where(
                BrandAsset.brand_id == brand_id,
                BrandAsset.sha256 == sha256,
            )
        )
        if existing is not None:
            existing.kind = kind
            existing.source_name = source_name
            existing.file_path = file_path
            existing.media_type = media_type
            existing.meta = meta
            # Wipe derived chunks so re-ingest doesn't stack duplicates.
            for chunk in list(existing.text_chunks):
                session.delete(chunk)
            for chunk in list(existing.image_chunks):
                session.delete(chunk)
            session.flush()
            return existing

    asset = BrandAsset(
        brand_id=brand_id,
        kind=kind,
        source_name=source_name,
        file_path=file_path,
        media_type=media_type,
        sha256=sha256,
        meta=meta,
    )
    session.add(asset)
    session.flush()
    return asset


# --- Text ingestion ------------------------------------------------------

async def ingest_text(
    *,
    brand: Brand,
    text: str,
    source: str,
    session: Session,
    kind: BrandTextKind = BrandTextKind.DOC,
    asset: BrandAsset | None = None,
    meta: dict | None = None,
) -> IngestResult:
    """Chunk + embed `text`, persist as `BrandTextChunk` rows."""
    chunks = chunk_text(text)
    if not chunks:
        return IngestResult(asset_id=asset.id if asset else 0)

    embeddings = await _embed_text(chunks)
    if asset is None:
        asset = _upsert_asset(
            session,
            brand_id=brand.id,
            kind=BrandAssetKind.TEXT,
            source_name=source,
            file_path=None,
            media_type="text/plain",
            sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
            meta=meta,
        )
    for chunk_text_, embedding in zip(chunks, embeddings, strict=True):
        session.add(
            BrandTextChunk(
                brand_id=brand.id,
                asset_id=asset.id,
                kind=kind,
                source=source,
                text=chunk_text_,
                embedding=embedding,
                meta=meta,
            )
        )
    session.flush()
    return IngestResult(asset_id=asset.id, text_chunks=len(chunks))


async def ingest_pdf(
    *,
    brand: Brand,
    pdf_bytes: bytes,
    source_name: str,
    session: Session,
) -> IngestResult:
    """Extract text from a PDF, chunk, embed, and persist."""
    sha256 = hashlib.sha256(pdf_bytes).hexdigest()
    file_path = _persist_bytes(pdf_bytes, brand.slug, "pdfs", sha256, ".pdf")
    asset = _upsert_asset(
        session,
        brand_id=brand.id,
        kind=BrandAssetKind.PDF,
        source_name=source_name,
        file_path=str(file_path),
        media_type="application/pdf",
        sha256=sha256,
    )
    text = extract_pdf_text(pdf_bytes)
    if not text:
        _LOG.warning("PDF %s yielded no extractable text", source_name)
        return IngestResult(asset_id=asset.id)
    return await ingest_text(
        brand=brand,
        text=text,
        source=source_name,
        session=session,
        kind=BrandTextKind.DOC,
        asset=asset,
    )


async def ingest_voice_pair(
    *,
    brand: Brand,
    do: str,
    dont: str,
    session: Session,
    source: str = "voice_pair",
) -> IngestResult:
    """Embed a do/don't pair as two `BrandTextChunk` rows with the right kind tags."""
    combined = f"DO: {do}\nDONT: {dont}"
    sha256 = hashlib.sha256(combined.encode("utf-8")).hexdigest()
    asset = _upsert_asset(
        session,
        brand_id=brand.id,
        kind=BrandAssetKind.VOICE,
        source_name=source,
        file_path=None,
        media_type="text/plain",
        sha256=sha256,
        meta={"do": do, "dont": dont},
    )
    embeddings = await _embed_text([do, dont])
    session.add(
        BrandTextChunk(
            brand_id=brand.id,
            asset_id=asset.id,
            kind=BrandTextKind.VOICE_DO,
            source=source,
            text=do,
            embedding=embeddings[0],
            meta={"pair_dont": dont},
        )
    )
    session.add(
        BrandTextChunk(
            brand_id=brand.id,
            asset_id=asset.id,
            kind=BrandTextKind.VOICE_DONT,
            source=source,
            text=dont,
            embedding=embeddings[1],
            meta={"pair_do": do},
        )
    )
    session.flush()
    return IngestResult(asset_id=asset.id, text_chunks=2)


# --- Image ingestion -----------------------------------------------------

def ingest_image(
    *,
    brand: Brand,
    image_bytes: bytes,
    source_name: str,
    session: Session,
    caption: str | None = None,
    kind: BrandAssetKind = BrandAssetKind.IMAGE,
    meta: dict | None = None,
) -> IngestResult:
    """Persist a brand reference image + its CLIP embedding + dominant palette.

    `kind` may be overridden (e.g. `BrandAssetKind.LOGO`) to distinguish
    the logo asset in the profile.
    """
    sha256 = hashlib.sha256(image_bytes).hexdigest()
    with Image.open(BytesIO(image_bytes)) as pil:
        pil = pil.convert("RGB")
        width, height = pil.size
        palette = _dominant_palette(pil, k=5)
        # Re-open from bytes for a fresh handle before embedding.
        subdir = "images" if kind != BrandAssetKind.LOGO else "logos"
        ext = _extension_for(image_bytes)
        file_path = _persist_bytes(image_bytes, brand.slug, subdir, sha256, ext)

    router = get_router()
    with Image.open(file_path) as pil2:
        embedding = router.clip.embed_pil([pil2.convert("RGB")])[0]

    asset = _upsert_asset(
        session,
        brand_id=brand.id,
        kind=kind,
        source_name=source_name,
        file_path=str(file_path),
        media_type=f"image/{ext.lstrip('.')}",
        sha256=sha256,
        meta={"width_px": width, "height_px": height, **(meta or {})},
    )
    session.add(
        BrandImageChunk(
            brand_id=brand.id,
            asset_id=asset.id,
            image_path=str(file_path),
            caption=caption,
            palette_hex=palette,
            embedding=embedding,
            meta=meta,
        )
    )
    session.flush()

    # Convenience: if this is a logo, also stamp brand.logo_path for the
    # profile card so the wizard doesn't need to query image_chunks.
    if kind == BrandAssetKind.LOGO:
        brand.logo_path = str(file_path)

    return IngestResult(asset_id=asset.id, image_chunks=1)


# --- Palette / typography / persona / competitors ------------------------

def set_palette(
    *,
    brand: Brand,
    dominant_hex: list[str] | None = None,
    accent_hex: list[str] | None = None,
) -> None:
    """Overwrite the palette columns on the brand row."""
    if dominant_hex is not None:
        brand.palette_dominant_hex = [_normalise_hex(h) for h in dominant_hex if _normalise_hex(h)]
    if accent_hex is not None:
        brand.palette_accent_hex = [_normalise_hex(h) for h in accent_hex if _normalise_hex(h)]


def set_typography(*, brand: Brand, typography: dict[str, str]) -> None:
    brand.typography = dict(typography)


async def set_persona(*, brand: Brand, persona: str, session: Session) -> None:
    """Save the persona description and embed it as a retrievable chunk."""
    brand.persona = persona
    await ingest_text(
        brand=brand,
        text=persona,
        source="persona",
        session=session,
        kind=BrandTextKind.PERSONA,
    )


async def set_competitors(
    *,
    brand: Brand,
    competitors: list[str],
    session: Session,
) -> None:
    """Save the competitor list and embed each entry as a chunk."""
    brand.competitors = [c.strip() for c in competitors if c and c.strip()]
    if not brand.competitors:
        return
    joined = "\n".join(brand.competitors)
    await ingest_text(
        brand=brand,
        text=joined,
        source="competitors",
        session=session,
        kind=BrandTextKind.COMPETITOR,
    )


# --- Helpers -------------------------------------------------------------

async def _embed_text(chunks: list[str]) -> list[list[float]]:
    router = get_router()
    return await router.embed.embed_text(chunks)


def _normalise_hex(value: str) -> str:
    v = (value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        return ""
    try:
        int(v, 16)
    except ValueError:
        return ""
    return f"#{v.upper()}"


def _extension_for(image_bytes: bytes) -> str:
    """Guess an extension from magic bytes. Defaults to `.png`."""
    if image_bytes.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        return ".webp"
    return ".png"


def _dominant_palette(image: Image.Image, *, k: int = 5) -> list[str]:
    """Quantise an image to `k` colours and return them as hex strings.

    Pillow's `quantize(colors=k)` picks a good palette without needing sklearn.
    """
    thumb = image.copy()
    thumb.thumbnail((256, 256))
    quant = thumb.convert("RGB").quantize(colors=k)
    palette = quant.getpalette() or []
    color_counts = quant.getcolors() or []
    color_counts.sort(reverse=True)  # (count, index)
    hexes: list[str] = []
    for _, idx in color_counts[:k]:
        r, g, b = palette[idx * 3:idx * 3 + 3]
        hexes.append(f"#{r:02X}{g:02X}{b:02X}")
    return hexes
