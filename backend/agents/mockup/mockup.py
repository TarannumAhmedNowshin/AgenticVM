"""Mockup — Gemini image edit of the original photo, primed by orchestrator tips."""

from __future__ import annotations

from backend.agents._prompt import load_prompt

# The mockup.md file is an *instruction template*, not a chat system prompt.
# We still load it via the same helper so the convention stays uniform.
TEMPLATE = load_prompt(__file__)


def render_instruction(brand_voice: str, prioritised_actions: str) -> str:
    """Fill the `{{ … }}` placeholders in mockup.md's body."""
    return (
        TEMPLATE.system
        .replace("{{ brand_voice }}", brand_voice)
        .replace("{{ prioritised_actions }}", prioritised_actions)
    )


async def render_mockup() -> bytes:
    """TODO(Phase 4): call ModelRouter.gemini.edit_image with the filled template."""
    raise NotImplementedError("Mockup renderer lands in Phase 4")
