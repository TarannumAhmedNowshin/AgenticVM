"""Shared contracts for specialist output tips."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Specialist = Literal["creative", "psychology", "commercial", "guardian"]


class Tip(BaseModel):
    """A single actionable recommendation from a specialist."""

    specialist: Specialist
    title: str
    rationale: str
    action: str
    confidence: float = Field(ge=0.0, le=1.0)
    references: list[str] = Field(default_factory=list)


class SpecialistOutput(BaseModel):
    specialist: Specialist
    tips: list[Tip]
