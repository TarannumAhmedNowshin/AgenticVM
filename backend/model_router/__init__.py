"""ModelRouter: unified interface over Claude / Azure embeddings / CLIP / Gemini."""

from backend.model_router.router import ModelRouter, get_router

__all__ = ["ModelRouter", "get_router"]
