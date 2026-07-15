"""Perception agent — image → SceneGraph.

Wires the Claude vision call defined in `perception.md` (system prompt) into
a fully-populated `SceneGraph`. Downstream product matching happens in
`backend.brand.product_matcher` and is called separately.

Uses Anthropic's tool-use API so Claude is forced to return JSON that
matches the SceneGraph schema — no fragile prose parsing.
"""

from __future__ import annotations

import hashlib
import logging
from io import BytesIO

from PIL import Image
from pydantic import ValidationError

from backend.agents._prompt import load_prompt
from backend.agents.perception.scene_graph import SCENE_GRAPH_TOOL_SCHEMA, SceneGraph
from backend.model_router.router import get_router

PROMPT = load_prompt(__file__)
_LOG = logging.getLogger(__name__)

# Short deterministic tag for the prompt file, stamped on every SceneGraph so
# downstream analyses can reproduce the exact perception input.
PROMPT_VERSION: str = hashlib.sha256(PROMPT.system.encode("utf-8")).hexdigest()[:12]

_TOOL_NAME = "submit_scene_graph"
_TOOL_DESCRIPTION = (
    "Record the structured description of the retail display in the image. "
    "Bounding boxes must be relative to the image (0..1). "
    "Return every visible product and every readable piece of text."
)


class PerceptionError(RuntimeError):
    """Raised when the vision response cannot be turned into a SceneGraph."""


async def perceive(
    image_bytes: bytes,
    *,
    image_id: str,
    media_type: str = "image/jpeg",
) -> SceneGraph:
    """Run Claude vision on `image_bytes` and return a validated `SceneGraph`.

    The returned graph has no matched SKUs — call
    `backend.brand.product_matcher.match_scene_products` afterwards to enrich
    it against a brand catalogue.
    """
    router = get_router()
    model = PROMPT.model or router.claude.default_model
    try:
        payload = await router.claude.vision_tool(
            system=PROMPT.system,
            image_bytes=image_bytes,
            media_type=media_type,
            tool_name=_TOOL_NAME,
            tool_description=_TOOL_DESCRIPTION,
            input_schema=SCENE_GRAPH_TOOL_SCHEMA,
            model=model,
            max_tokens=PROMPT.max_tokens or 2048,
        )
    except RuntimeError as exc:
        raise PerceptionError(str(exc)) from exc

    width, height = _image_dimensions(image_bytes)
    try:
        return SceneGraph.model_validate(
            {
                **payload,
                "image_id": image_id,
                "width_px": width,
                "height_px": height,
                "prompt_version": PROMPT_VERSION,
                "model_id": model,
            }
        )
    except ValidationError as exc:
        _LOG.warning("Perception validation failed: %s", exc)
        raise PerceptionError(f"SceneGraph validation failed: {exc}") from exc


def _image_dimensions(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(BytesIO(image_bytes)) as img:
            return img.width, img.height
    except Exception:  # noqa: BLE001 — best-effort metadata
        return None, None


