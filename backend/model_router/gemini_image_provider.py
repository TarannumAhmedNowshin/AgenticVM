"""Google Gemini image editing provider (for the after-mockup)."""

from __future__ import annotations

import base64
from io import BytesIO

from backend.config import get_settings


class GeminiImageProvider:
    """Wraps Gemini 2.5 Flash Image for text-guided edits of an existing photo."""

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.gemini_api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self._api_key = settings.gemini_api_key
        self._model_name = settings.gemini_image_model

        # Deferred import — google-generativeai is only needed when this provider is used.
        import google.generativeai as genai  # type: ignore[import-not-found]

        genai.configure(api_key=self._api_key)
        self._client = genai.GenerativeModel(self._model_name)

    async def edit_image(self, image_bytes: bytes, instruction: str) -> bytes:
        """Edit `image_bytes` per `instruction`, return the new PNG bytes."""
        response = await self._client.generate_content_async(
            [
                {"mime_type": "image/png", "data": image_bytes},
                instruction,
            ]
        )
        # Response may include either inline_data (base64 PNG) or a URL. Prefer inline.
        for part in response.candidates[0].content.parts:
            inline = getattr(part, "inline_data", None)
            if inline and inline.data:
                data = inline.data
                if isinstance(data, str):
                    data = base64.b64decode(data)
                return bytes(data)
        raise RuntimeError("Gemini image response contained no inline image data")

    @staticmethod
    def bytes_from_pil(image, format: str = "PNG") -> bytes:  # pragma: no cover
        buf = BytesIO()
        image.save(buf, format=format)
        return buf.getvalue()
