"""Shared helpers for agent modules.

Convention: each agent lives as a `<name>.py` file next to a `<name>.md`
file. The `.md` holds the system prompt (Markdown for readability; the
first `---` YAML frontmatter block, if present, holds tunable metadata
like `model` and `max_tokens`). The `.py` file loads its sibling with
`load_prompt(__file__)`.

This separates prompt engineering from code — prompts can be diffed,
reviewed, and edited without touching Python.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml  # PyYAML is a transitive dep of many libs; add explicitly if needed.


@dataclass(frozen=True)
class AgentPrompt:
    """Loaded prompt + optional YAML frontmatter metadata."""

    system: str
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def model(self) -> str | None:
        return self.meta.get("model")

    @property
    def max_tokens(self) -> int | None:
        value = self.meta.get("max_tokens")
        return int(value) if value is not None else None


def load_prompt(module_file: str, name: str | None = None) -> AgentPrompt:
    """Load the sibling `.md` prompt of the given module.

    Usage:
        PROMPT = load_prompt(__file__)              # loads <module_stem>.md
        PROMPT = load_prompt(__file__, "creative")  # loads creative.md
    """
    module_path = Path(module_file)
    stem = name or module_path.stem
    prompt_path = module_path.with_name(f"{stem}.md")
    if not prompt_path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    raw = prompt_path.read_text(encoding="utf-8")
    meta, body = _split_frontmatter(raw)
    return AgentPrompt(system=body.strip(), meta=meta)


def _split_frontmatter(raw: str) -> tuple[dict[str, Any], str]:
    """Extract a leading `---\\n...\\n---` YAML frontmatter block, if present."""
    if not raw.startswith("---"):
        return {}, raw
    parts = raw.split("---", 2)
    if len(parts) < 3:
        return {}, raw
    _, front, body = parts
    try:
        meta = yaml.safe_load(front) or {}
    except yaml.YAMLError:
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body
