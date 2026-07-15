"""Orchestrator — merges 9 draft tips + Guardian review into final deliverable."""

from __future__ import annotations

from backend.agents._prompt import load_prompt

PROMPT = load_prompt(__file__)


async def finalise() -> dict:
    """TODO(Phase 3): call Claude Opus with PROMPT.system + all specialist outputs."""
    raise NotImplementedError("Orchestrator lands in Phase 3")
