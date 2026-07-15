"""Brand Guardian — critiques the 9 draft tips against brand guardrails."""

from __future__ import annotations

from backend.agents._prompt import load_prompt

PROMPT = load_prompt(__file__)


async def review() -> dict:
    """TODO(Phase 3): call Claude with PROMPT.system + draft tips + guardrails."""
    raise NotImplementedError("Brand Guardian lands in Phase 3")
