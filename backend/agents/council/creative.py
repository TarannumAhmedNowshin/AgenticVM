"""Creative Specialist — aesthetics, composition, colour, storytelling."""

from __future__ import annotations

from backend.agents._prompt import load_prompt

PROMPT = load_prompt(__file__)


async def critique() -> list["Tip"]:  # type: ignore[name-defined]  # noqa: F821
    """TODO(Phase 3): call Claude with PROMPT.system + SceneGraph + BrandProfile."""
    raise NotImplementedError("Creative specialist lands in Phase 3")
