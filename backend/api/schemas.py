"""Pydantic schemas for API request / response bodies."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    is_active: bool
    created_at: datetime


class DisplayOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    image_sha256: str
    media_type: str
    width_px: int | None = None
    height_px: int | None = None
    created_at: datetime


class AnalysisOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    display_id: int
    status: str
    scene_graph: dict[str, Any] | None = None
    prompt_version: str | None = None
    model_id: str | None = None
    error: str | None = None
    created_at: datetime
    updated_at: datetime


class AnalyzeResponse(BaseModel):
    display: DisplayOut
    analysis: AnalysisOut


# --- Brand knowledge base -------------------------------------------------

class BrandCreateRequest(BaseModel):
    slug: str = Field(min_length=2, max_length=64, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=1, max_length=255)
    voice: str | None = None
    guardrails: str | None = None


class BrandProfileUpdate(BaseModel):
    """Partial update. `None` fields are left untouched; empty lists clear."""

    name: str | None = None
    voice: str | None = None
    guardrails: str | None = None
    palette_dominant_hex: list[str] | None = None
    palette_accent_hex: list[str] | None = None
    typography: dict[str, str] | None = None


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    name: str
    voice: str | None = None
    guardrails: str | None = None
    logo_path: str | None = None
    palette_dominant_hex: list[str] | None = None
    palette_accent_hex: list[str] | None = None
    typography: dict[str, str] | None = None
    persona: str | None = None
    competitors: list[str] | None = None
    created_at: datetime
    updated_at: datetime


class TextIngestRequest(BaseModel):
    text: str = Field(min_length=1)
    source: str = Field(min_length=1, max_length=255, default="user_text")


class VoicePairRequest(BaseModel):
    do: str = Field(min_length=1)
    dont: str = Field(min_length=1)


class PersonaRequest(BaseModel):
    persona: str = Field(min_length=1)


class CompetitorsRequest(BaseModel):
    competitors: list[str] = Field(default_factory=list)


class IngestResponse(BaseModel):
    asset_id: int
    text_chunks: int = 0
    image_chunks: int = 0


class BrandUnderstandingResponse(BaseModel):
    score: int
    breakdown: dict[str, int]


class BrandRetrieveRequest(BaseModel):
    query: str = Field(min_length=1)
    scene_palette: list[str] | None = None
    text_k: int = Field(default=4, ge=1, le=20)
    voice_k: int = Field(default=3, ge=1, le=20)
    image_k: int = Field(default=3, ge=1, le=20)


class TextHitOut(BaseModel):
    chunk_id: int
    text: str
    source: str | None = None
    kind: str
    score: float
    meta: dict[str, Any] | None = None


class ImageHitOut(BaseModel):
    chunk_id: int
    image_path: str
    caption: str | None = None
    palette_hex: list[str] = Field(default_factory=list)
    score: float
    meta: dict[str, Any] | None = None


class BrandContextResponse(BaseModel):
    text_snippets: list[TextHitOut] = Field(default_factory=list)
    voice_dos: list[TextHitOut] = Field(default_factory=list)
    voice_donts: list[TextHitOut] = Field(default_factory=list)
    reference_images: list[ImageHitOut] = Field(default_factory=list)
    palette_hints: list[str] = Field(default_factory=list)
