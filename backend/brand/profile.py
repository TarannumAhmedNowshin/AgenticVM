"""Brand profile schema.

`BrandProfile` is the agent-facing view of a brand's identity + audience. It's
derived from the DB `Brand` row plus small pieces of aggregated context
(counts, understanding score) and is what the council agents consume when
they need to reason about brand fit.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class VoicePair(BaseModel):
    """A single do/don't voice example. Used to steer copy tone."""

    do: str
    dont: str


class BrandIdentity(BaseModel):
    """Visual identity — palette, typography, logo."""

    logo_path: str | None = None
    palette_dominant_hex: list[str] = Field(default_factory=list)
    palette_accent_hex: list[str] = Field(default_factory=list)
    typography: dict[str, str] = Field(default_factory=dict)


class BrandAudience(BaseModel):
    persona: str | None = None
    competitors: list[str] = Field(default_factory=list)


class BrandProfile(BaseModel):
    """Full agent-facing brand profile."""

    model_config = ConfigDict(from_attributes=False)

    id: int
    slug: str
    name: str
    voice_description: str | None = None
    guardrails: str | None = None

    identity: BrandIdentity = Field(default_factory=BrandIdentity)
    audience: BrandAudience = Field(default_factory=BrandAudience)

    # Counts of ingested knowledge — used by the wizard to reason about
    # completeness. The full chunk bodies live in the DB and are retrieved
    # via `BrandRAG`, not carried on the profile.
    text_chunk_count: int = 0
    image_chunk_count: int = 0
    asset_count: int = 0
    voice_do_count: int = 0
    voice_dont_count: int = 0
