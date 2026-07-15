"""Provider protocols and shared types."""

from __future__ import annotations

from typing import Any, Protocol


class ChatProvider(Protocol):
    """Text/vision chat model provider."""

    async def chat(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        model: str | None = None,
        max_tokens: int = 1024,
        response_json: bool = False,
    ) -> str:
        ...


class TextEmbeddingProvider(Protocol):
    """Produces text embedding vectors."""

    async def embed_text(self, inputs: list[str]) -> list[list[float]]:
        ...


class ImageEmbeddingProvider(Protocol):
    """Produces image embedding vectors from PIL images or file paths."""

    def embed_image(self, image_paths: list[str]) -> list[list[float]]:
        ...


class ImageEditProvider(Protocol):
    """Edits an image based on a text instruction, returns PNG bytes."""

    async def edit_image(self, image_bytes: bytes, instruction: str) -> bytes:
        ...
