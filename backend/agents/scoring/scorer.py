"""Scorer — rubric-driven scoring of a SceneGraph (before + after)."""

from __future__ import annotations

from backend.agents._prompt import load_prompt

PROMPT = load_prompt(__file__)


async def score() -> dict:
    """TODO(Phase 4): call Claude with PROMPT.system + SceneGraph + rubric."""
    raise NotImplementedError("Scorer lands in Phase 4")
