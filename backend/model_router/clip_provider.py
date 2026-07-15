"""Local CLIP image-embedding provider.

Uses `open_clip_torch` to embed product photos into vectors that match against
the brand catalogue index in pgvector. Runs on CPU by default.
"""

from __future__ import annotations

from pathlib import Path
from typing import cast

import torch
from PIL import Image

from backend.config import get_settings


class CLIPProvider:
    """Lazily loads a CLIP model and embeds images from disk paths."""

    def __init__(self) -> None:
        settings = get_settings()
        self._model_name = settings.clip_model_name
        self._pretrained = settings.clip_pretrained
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

        # Deferred import so pytest collection doesn't pay the load cost.
        import open_clip  # type: ignore[import-not-found]

        self._model, _, self._preprocess = open_clip.create_model_and_transforms(
            self._model_name,
            pretrained=self._pretrained,
            device=self._device,
        )
        self._model.eval()

    @property
    def dimensions(self) -> int:
        # ViT-B/32 → 512-dim embeddings.
        return int(self._model.visual.output_dim)

    def embed_image(self, image_paths: list[str]) -> list[list[float]]:
        if not image_paths:
            return []
        images = [Image.open(Path(p)).convert("RGB") for p in image_paths]
        return self.embed_pil(images)

    def embed_pil(self, images: list[Image.Image]) -> list[list[float]]:
        """Embed a batch of already-loaded PIL images. Vectors are L2-normalised."""
        if not images:
            return []
        tensors = [self._preprocess(img.convert("RGB")) for img in images]
        batch = torch.stack(tensors).to(self._device)

        with torch.no_grad():
            features = self._model.encode_image(batch)
            features = features / features.norm(dim=-1, keepdim=True)

        return cast(list[list[float]], features.cpu().tolist())
