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


class AnalysisStatus(str, PyEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"


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

    products: Mapped[list[Product]] = relationship(
        back_populates="brand", cascade="all, delete-orphan"
    )
    displays: Mapped[list[Display]] = relationship(
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

