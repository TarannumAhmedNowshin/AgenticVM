"""Anthropic Claude provider."""

from __future__ import annotations

import base64
from typing import Any

from anthropic import AsyncAnthropic

from backend.config import get_settings


class ClaudeProvider:
    """Thin async wrapper around the Anthropic SDK.

    Model selection is left to the caller (perception, specialists, orchestrator, guardian)
    so we can route Sonnet / Haiku / Opus per agent.
    """

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self._client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._default_model = settings.claude_model
        self._orchestrator_model = settings.claude_orchestrator_model
        self._small_model = settings.claude_small_model

    @property
    def default_model(self) -> str:
        return self._default_model

    @property
    def orchestrator_model(self) -> str:
        return self._orchestrator_model

    @property
    def small_model(self) -> str:
        return self._small_model

    async def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int = 1024,
        response_json: bool = False,  # noqa: ARG002 (reserved for future tool use)
    ) -> str:
        """Send a chat request and return the raw text response.

        `messages` follows Anthropic's schema:
            [{"role": "user", "content": [{"type": "text", "text": "..."}]}]
        """
        response = await self._client.messages.create(
            model=model or self._default_model,
            system=system,
            messages=messages,
            max_tokens=max_tokens,
        )
        # Anthropic returns a list of content blocks; concatenate all text blocks.
        parts: list[str] = []
        for block in response.content:
            if getattr(block, "type", None) == "text":
                parts.append(block.text)
        return "".join(parts)

    async def vision(
        self,
        *,
        system: str,
        image_bytes: bytes,
        media_type: str = "image/jpeg",
        user_text: str = (
            "Analyse this retail display photograph and return the SceneGraph "
            "JSON described in the system prompt. Respond with JSON only."
        ),
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> str:
        """Send an image + prompt to Claude vision and return the raw text response.

        The caller is responsible for parsing JSON out of the response.
        """
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        return await self.chat(
            system=system,
            model=model,
            max_tokens=max_tokens,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )

    async def vision_tool(
        self,
        *,
        system: str,
        image_bytes: bytes,
        tool_name: str,
        tool_description: str,
        input_schema: dict[str, Any],
        media_type: str = "image/jpeg",
        user_text: str = (
            "Analyse this retail display photograph and call the provided tool "
            "with the structured result. Do not respond in prose."
        ),
        model: str | None = None,
        max_tokens: int = 2048,
    ) -> dict[str, Any]:
        """Send an image and force Claude to reply via a tool call.

        Returns the tool call's parsed `input` dict. Anthropic validates the
        model's response against `input_schema` on the server side, so this is
        the reliable way to get structured JSON.
        """
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        response = await self._client.messages.create(
            model=model or self._default_model,
            system=system,
            max_tokens=max_tokens,
            tools=[
                {
                    "name": tool_name,
                    "description": tool_description,
                    "input_schema": input_schema,
                }
            ],
            tool_choice={"type": "tool", "name": tool_name},
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": media_type,
                                "data": b64,
                            },
                        },
                        {"type": "text", "text": user_text},
                    ],
                }
            ],
        )
        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and block.name == tool_name:
                # `.input` is already a parsed dict per Anthropic SDK.
                return dict(block.input)
        raise RuntimeError(
            f"Claude did not return a {tool_name!r} tool call "
            f"(stop_reason={response.stop_reason})"
        )
