"""Brand RAG retriever — hybrid search over a brand's knowledge base.

Combines three signals per query:

* **Vector** — cosine distance on either Azure text embeddings
  (`brand_text_chunks`) or CLIP image embeddings (`brand_image_chunks`).
* **Keyword** — case-insensitive substring match on the chunk body.
* **Colour distance** — Euclidean distance in RGB space between a query
  palette and each chunk's stored dominant palette.

`retrieve_brand_context()` is the one-shot convenience the agents call — it
returns a fully-populated `BrandContext` bundle with text snippets,
reference images, voice pairs, and palette hints. Individual retrievers are
also exported for finer-grained callers (debug UI, tests).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.db.models import (
    Brand,
    BrandImageChunk,
    BrandTextChunk,
    BrandTextKind,
)
from backend.model_router.router import get_router

_LOG = logging.getLogger(__name__)


# --- Result types --------------------------------------------------------

@dataclass
class TextHit:
    chunk_id: int
    text: str
    source: str | None
    kind: BrandTextKind
    score: float  # 0..1, higher = better
    meta: dict | None = None


@dataclass
class ImageHit:
    chunk_id: int
    image_path: str
    caption: str | None
    palette_hex: list[str]
    score: float
    meta: dict | None = None


@dataclass
class BrandContext:
    """Bundle handed to specialist agents when they need brand context."""

    text_snippets: list[TextHit] = field(default_factory=list)
    voice_dos: list[TextHit] = field(default_factory=list)
    voice_donts: list[TextHit] = field(default_factory=list)
    reference_images: list[ImageHit] = field(default_factory=list)
    palette_hints: list[str] = field(default_factory=list)


# --- Public API ----------------------------------------------------------

async def retrieve_text(
    *,
    brand_id: int,
    query: str,
    session: Session,
    k: int = 5,
    kinds: Iterable[BrandTextKind] | None = None,
    keyword_weight: float = 0.25,
) -> list[TextHit]:
    """Hybrid vector + keyword text retrieval over `brand_text_chunks`.

    Vector score is `1 - cosine_distance` (so higher = better). Keyword hits
    get a flat bonus of `keyword_weight`. Missing embeddings fall back to
    keyword-only.
    """
    if not query or not query.strip():
        return []
    router = get_router()
    try:
        embedding = (await router.embed.embed_text([query]))[0]
    except Exception as exc:  # noqa: BLE001
        _LOG.warning("Text embedding failed, falling back to keyword-only: %s", exc)
        embedding = None

    filters = [BrandTextChunk.brand_id == brand_id]
    if kinds:
        filters.append(BrandTextChunk.kind.in_(list(kinds)))

    hits: dict[int, TextHit] = {}

    if embedding is not None:
        distance = BrandTextChunk.embedding.cosine_distance(embedding).label("distance")
        stmt = (
            select(BrandTextChunk, distance)
            .where(*filters, BrandTextChunk.embedding.is_not(None))
            .order_by("distance")
            .limit(k * 3)
        )
        for chunk, dist in session.execute(stmt).all():
            similarity = max(0.0, 1.0 - float(dist))
            hits[chunk.id] = TextHit(
                chunk_id=chunk.id,
                text=chunk.text,
                source=chunk.source,
                kind=chunk.kind,
                score=similarity,
                meta=chunk.meta,
            )

    # Keyword boost: substring match on the query's most distinctive words.
    keywords = _keywords(query)
    if keywords:
        clauses = [BrandTextChunk.text.ilike(f"%{kw}%") for kw in keywords]
        kw_stmt = (
            select(BrandTextChunk).where(*filters, or_(*clauses)).limit(k * 3)
        )
        for chunk in session.scalars(kw_stmt).all():
            existing = hits.get(chunk.id)
            if existing is None:
                hits[chunk.id] = TextHit(
                    chunk_id=chunk.id,
                    text=chunk.text,
                    source=chunk.source,
                    kind=chunk.kind,
                    score=keyword_weight,
                    meta=chunk.meta,
                )
            else:
                existing.score = min(1.0, existing.score + keyword_weight)

    ranked = sorted(hits.values(), key=lambda h: h.score, reverse=True)
    return ranked[:k]


def retrieve_images_by_embedding(
    *,
    brand_id: int,
    embedding: list[float],
    session: Session,
    k: int = 5,
) -> list[ImageHit]:
    """Nearest-neighbour lookup on `brand_image_chunks` by CLIP embedding."""
    distance = BrandImageChunk.embedding.cosine_distance(embedding).label("distance")
    stmt = (
        select(BrandImageChunk, distance)
        .where(
            BrandImageChunk.brand_id == brand_id,
            BrandImageChunk.embedding.is_not(None),
        )
        .order_by("distance")
        .limit(k)
    )
    hits: list[ImageHit] = []
    for chunk, dist in session.execute(stmt).all():
        hits.append(
            ImageHit(
                chunk_id=chunk.id,
                image_path=chunk.image_path,
                caption=chunk.caption,
                palette_hex=list(chunk.palette_hex or []),
                score=max(0.0, 1.0 - float(dist)),
                meta=chunk.meta,
            )
        )
    return hits


def retrieve_images_by_color(
    *,
    brand_id: int,
    palette_hex: list[str],
    session: Session,
    k: int = 5,
) -> list[ImageHit]:
    """Rank brand reference images by RGB distance to `palette_hex`.

    Colour distance is computed in Python because pgvector doesn't natively
    do palette-set distance. Fine for brand-scale catalogues (typically
    <500 reference images per brand).
    """
    if not palette_hex:
        return []
    query_rgb = [c for c in (_hex_to_rgb(h) for h in palette_hex) if c is not None]
    if not query_rgb:
        return []

    stmt = select(BrandImageChunk).where(
        BrandImageChunk.brand_id == brand_id,
        BrandImageChunk.palette_hex.is_not(None),
    )
    hits: list[tuple[float, BrandImageChunk]] = []
    for chunk in session.scalars(stmt).all():
        chunk_rgb = [c for c in (_hex_to_rgb(h) for h in (chunk.palette_hex or []))
                     if c is not None]
        if not chunk_rgb:
            continue
        distance = _palette_distance(query_rgb, chunk_rgb)
        hits.append((distance, chunk))
    hits.sort(key=lambda pair: pair[0])
    top = hits[:k]
    # Normalise distance → 0..1 similarity (441 ≈ max RGB distance).
    return [
        ImageHit(
            chunk_id=chunk.id,
            image_path=chunk.image_path,
            caption=chunk.caption,
            palette_hex=list(chunk.palette_hex or []),
            score=max(0.0, 1.0 - min(distance / 441.0, 1.0)),
            meta=chunk.meta,
        )
        for distance, chunk in top
    ]


async def retrieve_brand_context(
    *,
    brand: Brand,
    query: str,
    session: Session,
    scene_palette: list[str] | None = None,
    text_k: int = 4,
    voice_k: int = 3,
    image_k: int = 3,
) -> BrandContext:
    """One-shot bundle used by council agents.

    * `query` — freeform description of the display (usually a caption
      summarising the SceneGraph).
    * `scene_palette` — dominant hex colours detected in the scene; used
      for the colour-distance ranker over brand reference images.
    """
    text_snippets = await retrieve_text(
        brand_id=brand.id, query=query, session=session, k=text_k,
        kinds=[BrandTextKind.DOC, BrandTextKind.PERSONA, BrandTextKind.COMPETITOR],
    )
    voice_dos = await retrieve_text(
        brand_id=brand.id, query=query, session=session, k=voice_k,
        kinds=[BrandTextKind.VOICE_DO],
    )
    voice_donts = await retrieve_text(
        brand_id=brand.id, query=query, session=session, k=voice_k,
        kinds=[BrandTextKind.VOICE_DONT],
    )

    reference_images: list[ImageHit] = []
    if scene_palette:
        reference_images = retrieve_images_by_color(
            brand_id=brand.id, palette_hex=scene_palette, session=session, k=image_k
        )

    palette_hints: list[str] = []
    if brand.palette_dominant_hex:
        palette_hints.extend(brand.palette_dominant_hex)
    if brand.palette_accent_hex:
        palette_hints.extend(brand.palette_accent_hex)

    return BrandContext(
        text_snippets=text_snippets,
        voice_dos=voice_dos,
        voice_donts=voice_donts,
        reference_images=reference_images,
        palette_hints=palette_hints,
    )


def count_text_chunks(session: Session, brand_id: int,
                      kind: BrandTextKind | None = None) -> int:
    stmt = select(func.count(BrandTextChunk.id)).where(BrandTextChunk.brand_id == brand_id)
    if kind is not None:
        stmt = stmt.where(BrandTextChunk.kind == kind)
    return int(session.scalar(stmt) or 0)


def count_image_chunks(session: Session, brand_id: int) -> int:
    stmt = select(func.count(BrandImageChunk.id)).where(BrandImageChunk.brand_id == brand_id)
    return int(session.scalar(stmt) or 0)


# --- Helpers -------------------------------------------------------------

_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "and", "or", "of", "for", "to", "in", "on", "with",
    "is", "are", "at", "by", "this", "that", "it", "as", "be", "from",
})


def _keywords(query: str) -> list[str]:
    tokens = [t.lower() for t in query.split() if len(t) > 3]
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        cleaned = "".join(ch for ch in t if ch.isalnum())
        if not cleaned or cleaned in _STOPWORDS or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out[:5]


def _hex_to_rgb(value: str) -> tuple[int, int, int] | None:
    v = (value or "").strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        return None
    try:
        return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)
    except ValueError:
        return None


def _palette_distance(
    a: list[tuple[int, int, int]], b: list[tuple[int, int, int]]
) -> float:
    """Average nearest-neighbour Euclidean distance between two palettes."""
    def nearest(colour: tuple[int, int, int], palette: list[tuple[int, int, int]]) -> float:
        return min(
            ((colour[0] - c[0]) ** 2 + (colour[1] - c[1]) ** 2 + (colour[2] - c[2]) ** 2) ** 0.5
            for c in palette
        )

    if not a or not b:
        return float("inf")
    forward = sum(nearest(c, b) for c in a) / len(a)
    backward = sum(nearest(c, a) for c in b) / len(b)
    return (forward + backward) / 2.0
