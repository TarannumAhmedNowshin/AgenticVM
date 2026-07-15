"""Azure OpenAI text-embedding provider."""

from __future__ import annotations

from openai import AsyncAzureOpenAI

from backend.config import get_settings


def _endpoint_base(endpoint: str) -> str:
    """Extract the resource base from a deployment URL if a full URL was provided."""
    # The user's .env has the full "…/openai/deployments/…/embeddings?…" URL for EMBED_ENDPOINT.
    # AsyncAzureOpenAI expects just the resource base ("https://<resource>.openai.azure.com").
    marker = "/openai/deployments"
    if marker in endpoint:
        return endpoint.split(marker, 1)[0]
    return endpoint.rstrip("/")


class AzureEmbeddingProvider:
    """Wraps Azure OpenAI text embeddings (default: text-embedding-3-large, 3072 dims)."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.embed_api_key or not settings.embed_endpoint:
            raise RuntimeError("EMBED_API_KEY / EMBED_ENDPOINT are not set")

        self._client = AsyncAzureOpenAI(
            api_key=settings.embed_api_key,
            api_version=settings.embed_api_version,
            azure_endpoint=_endpoint_base(settings.embed_endpoint),
        )
        self._deployment = settings.embed_deployment
        self._dimensions = settings.embed_dimensions

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def embed_text(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        resp = await self._client.embeddings.create(
            model=self._deployment,
            input=inputs,
        )
        return [item.embedding for item in resp.data]
