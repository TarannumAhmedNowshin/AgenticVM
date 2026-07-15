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
