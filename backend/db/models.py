"""SQLAlchemy models.

Import this module (directly or via `from backend.db import models`) to ensure
all mappers are registered with `Base.metadata` before Alembic autogenerate runs.
"""

from __future__ import annotations

from enum import Enum as PyEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.db.base import Base, TimestampMixin

# CLIP ViT-B/32 embedding dimensionality. Kept in sync with `CLIPProvider`.
CLIP_DIM = 512

# Azure `text-embedding-3-large` dimensionality. Kept in sync with
# `AzureEmbeddingProvider` / `Settings.embed_dimensions`.
TEXT_EMBED_DIM = 3072


class AnalysisStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


class BrandAssetKind(str, PyEnum):
    """What kind of raw asset was ingested into a brand's knowledge base."""

    PDF = "pdf"
    IMAGE = "image"
    LOGO = "logo"
    TEXT = "text"
    VOICE = "voice"
    PALETTE = "palette"


class BrandTextKind(str, PyEnum):
    """Semantic tag for a text chunk so retrievers can filter by intent."""

    DOC = "doc"          # generic prose (brand book, marketing PDF)
    VOICE_DO = "voice_do"
    VOICE_DONT = "voice_dont"
    PERSONA = "persona"
    COMPETITOR = "competitor"
    OTHER = "other"


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r}>"


class Brand(Base, TimestampMixin):
    """A tenant brand. Owns products, brand assets, and displays."""

    __tablename__ = "brands"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    voice: Mapped[str | None] = mapped_column(Text, nullable=True)
    guardrails: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Brand profile (identity + audience) -----------------------------
    logo_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    palette_dominant_hex: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    palette_accent_hex: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    typography: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    persona: Mapped[str | None] = mapped_column(Text, nullable=True)
    competitors: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)

    products: Mapped[list[Product]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )
    displays: Mapped[list[Display]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )
    assets: Mapped[list[BrandAsset]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )
    text_chunks: Mapped[list[BrandTextChunk]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )
    image_chunks: Mapped[list[BrandImageChunk]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Brand id={self.id} slug={self.slug!r}>"


class Product(Base, TimestampMixin):
    """A single SKU in a brand's catalogue with an optional CLIP embedding."""

    __tablename__ = "products"
    __table_args__ = (UniqueConstraint("brand_id", "sku", name="uq_products_brand_sku"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    sku: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    price: Mapped[str | None] = mapped_column(String(32), nullable=True)
    image_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(CLIP_DIM), nullable=True)

    brand: Mapped[Brand] = relationship(back_populates="products")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Product id={self.id} sku={self.sku!r} brand_id={self.brand_id}>"


class Display(Base, TimestampMixin):
    """An uploaded retail-display photo tied to a brand + owning user."""

    __tablename__ = "displays"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    image_sha256: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    media_type: Mapped[str] = mapped_column(String(64), nullable=False)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)

    brand: Mapped[Brand] = relationship(back_populates="displays")
    analyses: Mapped[list[Analysis]] = relationship(
        back_populates="display", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Display id={self.id} brand_id={self.brand_id}>"


class Analysis(Base, TimestampMixin):
    """A single perception + council run against a display."""

    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_id: Mapped[int] = mapped_column(
        ForeignKey("displays.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    status: Mapped[AnalysisStatus] = mapped_column(
        SAEnum(AnalysisStatus, name="analysis_status", native_enum=False, length=32),
        default=AnalysisStatus.PENDING,
        nullable=False,
        index=True,
    )
    scene_graph: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    display: Mapped[Display] = relationship(back_populates="analyses")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Analysis id={self.id} status={self.status}>"


class BrandAsset(Base, TimestampMixin):
    """A raw file / document uploaded into a brand's knowledge base.

    The parsed / embedded output lives in `BrandTextChunk` and `BrandImageChunk`
    rows that reference this asset. Deleting an asset cascades to its chunks.
    """

    __tablename__ = "brand_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    kind: Mapped[BrandAssetKind] = mapped_column(
        SAEnum(BrandAssetKind, name="brand_asset_kind", native_enum=False, length=32),
        nullable=False,
    )
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    media_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), index=True, nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    brand: Mapped[Brand] = relationship(back_populates="assets")
    text_chunks: Mapped[list[BrandTextChunk]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )
    image_chunks: Mapped[list[BrandImageChunk]] = relationship(
        back_populates="asset", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BrandAsset id={self.id} brand_id={self.brand_id} kind={self.kind}>"


class BrandTextChunk(Base, TimestampMixin):
    """A retrievable text snippet embedded with Azure text-embedding-3-large."""

    __tablename__ = "brand_text_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("brand_assets.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    kind: Mapped[BrandTextKind] = mapped_column(
        SAEnum(BrandTextKind, name="brand_text_kind", native_enum=False, length=32),
        default=BrandTextKind.DOC,
        nullable=False,
        index=True,
    )
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(TEXT_EMBED_DIM), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    brand: Mapped[Brand] = relationship(back_populates="text_chunks")
    asset: Mapped[BrandAsset | None] = relationship(back_populates="text_chunks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BrandTextChunk id={self.id} brand_id={self.brand_id} kind={self.kind}>"


class BrandImageChunk(Base, TimestampMixin):
    """A reference / aesthetic image embedded with CLIP for image RAG."""

    __tablename__ = "brand_image_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    brand_id: Mapped[int] = mapped_column(
        ForeignKey("brands.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("brand_assets.id", ondelete="CASCADE"),
        index=True,
        nullable=True,
    )
    image_path: Mapped[str] = mapped_column(String(512), nullable=False)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)
    palette_hex: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(CLIP_DIM), nullable=True)
    meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    brand: Mapped[Brand] = relationship(back_populates="image_chunks")
    asset: Mapped[BrandAsset | None] = relationship(back_populates="image_chunks")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<BrandImageChunk id={self.id} brand_id={self.brand_id}>"

