"""BrandUnderstandingScore — 0..100 rollup of how well the brand is described.

Composed of five weighted signals so the brand wizard can nudge the operator
toward filling in what's missing. The exact weights are documented in
`AXIS_WEIGHTS` and kept small enough that reviewers can tune them without
re-training anything.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from backend.brand.rag import count_image_chunks, count_text_chunks
from backend.db.models import Brand, BrandTextKind


AXIS_WEIGHTS: dict[str, int] = {
    "identity": 20,     # logo + palette + typography
    "voice": 25,        # do/don't pairs
    "docs": 20,         # embedded text chunks (guidelines, brand book)
    "images": 20,       # aesthetic / reference images
    "audience": 15,     # persona + competitors
}

# Targets that award full points on each axis. Anything below scales linearly.
_TEXT_CHUNK_TARGET = 10
_IMAGE_CHUNK_TARGET = 5
_VOICE_PAIR_TARGET = 3
_COMPETITOR_TARGET = 3


@dataclass
class BrandUnderstandingBreakdown:
    identity: int
    voice: int
    docs: int
    images: int
    audience: int

    @property
    def total(self) -> int:
        return self.identity + self.voice + self.docs + self.images + self.audience

    def as_dict(self) -> dict[str, int]:
        return {
            "identity": self.identity,
            "voice": self.voice,
            "docs": self.docs,
            "images": self.images,
            "audience": self.audience,
            "total": self.total,
        }


def compute_understanding(brand: Brand, session: Session) -> BrandUnderstandingBreakdown:
    """Return the per-axis breakdown for `brand`. All integers, capped by weight."""
    identity = _score_identity(brand)
    voice_do = count_text_chunks(session, brand.id, BrandTextKind.VOICE_DO)
    voice_dont = count_text_chunks(session, brand.id, BrandTextKind.VOICE_DONT)
    voice_pairs = min(voice_do, voice_dont)
    voice = _scaled(voice_pairs, _VOICE_PAIR_TARGET, AXIS_WEIGHTS["voice"])

    doc_chunks = count_text_chunks(session, brand.id, BrandTextKind.DOC)
    docs = _scaled(doc_chunks, _TEXT_CHUNK_TARGET, AXIS_WEIGHTS["docs"])

    images = _scaled(
        count_image_chunks(session, brand.id), _IMAGE_CHUNK_TARGET, AXIS_WEIGHTS["images"]
    )

    audience = _score_audience(brand)

    return BrandUnderstandingBreakdown(
        identity=identity,
        voice=voice,
        docs=docs,
        images=images,
        audience=audience,
    )


def _score_identity(brand: Brand) -> int:
    """Logo (8) + palette-dominant (7) + typography (5) = 20."""
    score = 0
    if brand.logo_path:
        score += 8
    dominant = brand.palette_dominant_hex or []
    if len(dominant) >= 3:
        score += 7
    elif dominant:
        score += 3
    if brand.typography:
        score += 5
    return min(score, AXIS_WEIGHTS["identity"])


def _score_audience(brand: Brand) -> int:
    """Persona (10) + competitor list up to target (5) = 15."""
    score = 0
    if brand.persona and brand.persona.strip():
        score += 10
    competitors = brand.competitors or []
    score += _scaled(len(competitors), _COMPETITOR_TARGET, 5)
    return min(score, AXIS_WEIGHTS["audience"])


def _scaled(count: int, target: int, max_score: int) -> int:
    if target <= 0:
        return 0
    ratio = min(1.0, count / target)
    return int(round(ratio * max_score))
