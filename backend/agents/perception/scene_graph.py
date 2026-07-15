"""SceneGraph — normalised, agent-facing representation of a display photo.

Populated by the Perception agent and consumed by all council agents.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class BoundingBox(BaseModel):
    """Relative bounding box (0..1) in the source image."""

    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    w: float = Field(ge=0.0, le=1.0)
    h: float = Field(ge=0.0, le=1.0)


class DetectedProduct(BaseModel):
    label: str
    bbox: BoundingBox | None = None
    matched_sku: str | None = None
    matched_confidence: float | None = None
    price: str | None = None
    category: str | None = None


class DetectedText(BaseModel):
    text: str
    bbox: BoundingBox | None = None
    kind: str | None = None  # e.g. "price_tag", "shelf_talker", "signage"


class ScenePalette(BaseModel):
    dominant_hex: list[str] = Field(default_factory=list)
    accent_hex: list[str] = Field(default_factory=list)


class SceneZones(BaseModel):
    """Coarse spatial regions used by merchandising reasoning."""

    focal_points: list[BoundingBox] = Field(default_factory=list)
    eye_line_bbox: BoundingBox | None = None


class SceneGraph(BaseModel):
    """Everything downstream agents need to know about the display."""

    image_id: str
    width_px: int | None = None
    height_px: int | None = None
    prompt_version: str | None = None
    model_id: str | None = None

    products: list[DetectedProduct] = Field(default_factory=list)
    text: list[DetectedText] = Field(default_factory=list)
    palette: ScenePalette = Field(default_factory=ScenePalette)
    zones: SceneZones = Field(default_factory=SceneZones)
    lighting_notes: str | None = None
    composition_notes: str | None = None


# --- Anthropic tool-use schema -------------------------------------------
#
# Only the fields Claude should return. `image_id`, `width_px`, `height_px`,
# `prompt_version`, and `model_id` are stamped by `perceive()`, never by the
# model.

_BBOX_SCHEMA = {
    "type": "object",
    "description": "Bounding box with values relative to the image (0..1).",
    "properties": {
        "x": {"type": "number", "minimum": 0, "maximum": 1},
        "y": {"type": "number", "minimum": 0, "maximum": 1},
        "w": {"type": "number", "minimum": 0, "maximum": 1},
        "h": {"type": "number", "minimum": 0, "maximum": 1},
    },
    "required": ["x", "y", "w", "h"],
    "additionalProperties": False,
}


SCENE_GRAPH_TOOL_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "products": {
            "type": "array",
            "description": "Every distinct product visible in the display.",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "bbox": _BBOX_SCHEMA,
                    "category": {"type": "string"},
                    "price": {"type": "string"},
                },
                "required": ["label"],
                "additionalProperties": False,
            },
        },
        "text": {
            "type": "array",
            "description": "All readable text in the scene (signage, price tags, shelf talkers).",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "bbox": _BBOX_SCHEMA,
                    "kind": {
                        "type": "string",
                        "enum": ["price_tag", "shelf_talker", "signage", "other"],
                    },
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
        "palette": {
            "type": "object",
            "properties": {
                "dominant_hex": {"type": "array", "items": {"type": "string"}},
                "accent_hex": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["dominant_hex", "accent_hex"],
            "additionalProperties": False,
        },
        "zones": {
            "type": "object",
            "properties": {
                "focal_points": {"type": "array", "items": _BBOX_SCHEMA},
                "eye_line_bbox": _BBOX_SCHEMA,
            },
            "required": ["focal_points"],
            "additionalProperties": False,
        },
        "lighting_notes": {"type": "string"},
        "composition_notes": {"type": "string"},
    },
    "required": ["products", "text", "palette", "zones"],
    "additionalProperties": False,
}
