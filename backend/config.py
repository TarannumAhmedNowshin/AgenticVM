"""Central runtime configuration loaded from environment / .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime settings.

    Reads from process environment first, then `.env` at the repo root.
    Unknown keys are ignored so upstream additions don't break startup.
    """

    model_config = SettingsConfigDict(
        env_file=str(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    app_env: str = "dev"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"

    # --- Storage ---
    storage_dir: Path = REPO_ROOT / "backend" / "storage"

    # --- Database ---
    database_url: str = "postgresql+psycopg://avms:avms@localhost:5432/avms"

    # --- Auth ---
    jwt_secret: str = "dev-secret-change-me"
    jwt_algorithm: str = "HS256"
    jwt_access_token_minutes: int = 60 * 24

    # --- Claude ---
    # Model IDs follow Anthropic's `claude-<family>-<version>-<YYYYMMDD>` convention.
    # Override in `.env` when new revisions ship — code should never hard-code these.
    anthropic_api_key: str | None = None
    claude_model: str = "claude-sonnet-4-5-20250929"
    claude_orchestrator_model: str = "claude-opus-4-1-20250805"
    claude_small_model: str = "claude-haiku-4-5-20251001"

    # --- Azure OpenAI (chat, optional) ---
    azure_api_key: str | None = None
    azure_api_version: str = "2024-12-01-preview"
    azure_deployment: str = "gpt-4o"
    azure_endpoint: str | None = None
    azure_model: str = "gpt-4o"

    # --- Azure OpenAI embeddings ---
    embed_api_key: str | None = None
    embed_api_version: str = "2024-12-01-preview"
    embed_deployment: str = "text-embedding-3-large"
    embed_endpoint: str | None = None
    embed_model: str = "text-embedding-3-large"
    embed_dimensions: int = 3072

    # --- Gemini image editing ---
    gemini_api_key: str | None = None
    gemini_image_model: str = "gemini-2.5-flash-image-preview"

    # --- Cloudflare fallback image gen ---
    cloudflare_account_id: str | None = None
    cloudflare_api_token: str | None = None
    cloudflare_image_model: str = "@cf/stabilityai/stable-diffusion-xl-base-1.0"

    # --- CLIP ---
    clip_model_name: str = "ViT-B-32"
    clip_pretrained: str = "openai"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    """Cached settings accessor. Call this rather than instantiating Settings directly."""
    settings = Settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    return settings
