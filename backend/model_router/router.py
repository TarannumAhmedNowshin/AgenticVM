"""Unified router: one accessor for all four providers.

Providers are lazily instantiated so a missing API key for an unused provider
never blocks app startup. Import once and pass around.
"""

from __future__ import annotations

from functools import lru_cache
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.model_router.azure_embedding_provider import AzureEmbeddingProvider
    from backend.model_router.claude_provider import ClaudeProvider
    from backend.model_router.clip_provider import CLIPProvider
    from backend.model_router.gemini_image_provider import GeminiImageProvider


class ModelRouter:
    """Facade over the four providers with lazy initialisation."""

    def __init__(self) -> None:
        self._claude: ClaudeProvider | None = None
        self._embed: AzureEmbeddingProvider | None = None
        self._clip: CLIPProvider | None = None
        self._gemini: GeminiImageProvider | None = None

    @property
    def claude(self) -> ClaudeProvider:
        if self._claude is None:
            from backend.model_router.claude_provider import ClaudeProvider

            self._claude = ClaudeProvider()
        return self._claude

    @property
    def embed(self) -> AzureEmbeddingProvider:
        if self._embed is None:
            from backend.model_router.azure_embedding_provider import AzureEmbeddingProvider

            self._embed = AzureEmbeddingProvider()
        return self._embed

    @property
    def clip(self) -> CLIPProvider:
        if self._clip is None:
            from backend.model_router.clip_provider import CLIPProvider

            self._clip = CLIPProvider()
        return self._clip

    @property
    def gemini(self) -> GeminiImageProvider:
        if self._gemini is None:
            from backend.model_router.gemini_image_provider import GeminiImageProvider

            self._gemini = GeminiImageProvider()
        return self._gemini


@lru_cache
def get_router() -> ModelRouter:
    """Cached global router instance."""
    return ModelRouter()
