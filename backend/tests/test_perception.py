"""Perception agent tests — mocks the Claude vision tool call."""

from __future__ import annotations

from io import BytesIO
from typing import Any

import pytest
from PIL import Image

from backend.agents.perception import perception
from backend.agents.perception.scene_graph import SceneGraph


def _tiny_png_bytes() -> bytes:
    buffer = BytesIO()
    Image.new("RGB", (32, 24), (200, 180, 160)).save(buffer, format="PNG")
    return buffer.getvalue()


class _FakeClaude:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []
        self.default_model = "claude-sonnet-4-5-20250929"

    async def vision_tool(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class _FakeRouter:
    def __init__(self, response: dict[str, Any] | Exception) -> None:
        self.claude = _FakeClaude(response)


@pytest.fixture
def fake_router(monkeypatch: pytest.MonkeyPatch):
    def _install(response: dict[str, Any] | Exception) -> _FakeRouter:
        router = _FakeRouter(response)
        monkeypatch.setattr(perception, "get_router", lambda: router)
        return router

    return _install


async def test_perceive_returns_scene_graph_from_tool_call(fake_router) -> None:
    payload = {
        "products": [
            {
                "label": "denim jacket",
                "bbox": {"x": 0.1, "y": 0.2, "w": 0.3, "h": 0.4},
                "category": "outerwear",
                "price": "$120",
            }
        ],
        "text": [
            {
                "text": "50% OFF",
                "bbox": {"x": 0.5, "y": 0.6, "w": 0.2, "h": 0.05},
                "kind": "signage",
            }
        ],
        "palette": {"dominant_hex": ["#112233"], "accent_hex": ["#aabbcc"]},
        "zones": {"focal_points": [{"x": 0.4, "y": 0.4, "w": 0.2, "h": 0.2}]},
        "lighting_notes": "Warm overhead spotlight from front-left.",
        "composition_notes": "Symmetric hero layout with generous negative space.",
    }
    router = fake_router(payload)

    scene = await perception.perceive(_tiny_png_bytes(), image_id="img-123")

    assert isinstance(scene, SceneGraph)
    assert scene.image_id == "img-123"
    assert scene.width_px == 32
    assert scene.height_px == 24
    assert scene.prompt_version == perception.PROMPT_VERSION
    assert scene.model_id  # populated from PROMPT.model or router default
    assert len(scene.products) == 1
    assert scene.products[0].label == "denim jacket"
    assert scene.products[0].bbox is not None
    assert scene.products[0].price == "$120"
    assert scene.palette.dominant_hex == ["#112233"]
    assert scene.lighting_notes and "spotlight" in scene.lighting_notes

    # Sanity: exactly one Claude call, with our tool wired up.
    assert len(router.claude.calls) == 1
    kwargs = router.claude.calls[0]
    assert kwargs["tool_name"] == "submit_scene_graph"
    assert kwargs["input_schema"]["properties"]["products"]["type"] == "array"


async def test_perceive_handles_empty_scene(fake_router) -> None:
    fake_router(
        {
            "products": [],
            "text": [],
            "palette": {"dominant_hex": [], "accent_hex": []},
            "zones": {"focal_points": []},
        }
    )
    scene = await perception.perceive(_tiny_png_bytes(), image_id="img-empty")
    assert scene.products == []
    assert scene.text == []


async def test_perceive_wraps_tool_call_errors(fake_router) -> None:
    fake_router(RuntimeError("Claude did not return a 'submit_scene_graph' tool call"))
    with pytest.raises(perception.PerceptionError):
        await perception.perceive(_tiny_png_bytes(), image_id="img-bad")


async def test_perceive_raises_on_schema_violation(fake_router) -> None:
    # bbox out of range should trip Pydantic validation.
    fake_router(
        {
            "products": [
                {"label": "x", "bbox": {"x": 5, "y": 0, "w": 0.1, "h": 0.1}},
            ],
            "text": [],
            "palette": {"dominant_hex": [], "accent_hex": []},
            "zones": {"focal_points": []},
        }
    )
    with pytest.raises(perception.PerceptionError):
        await perception.perceive(_tiny_png_bytes(), image_id="img-invalid")

