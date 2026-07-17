"""add brand knowledge base (profile columns + assets + text/image chunks)

Revision ID: e5b7f4d18a29
Revises: d92f3a1e6c47
Create Date: 2026-07-18 10:00:00.000000

Phase 2 of the AVMS roadmap. Adds:

* Extra profile columns on ``brands`` (logo, palette, typography, persona,
  competitors) so we can render the identity panel in the brand wizard.
* ``brand_assets`` — raw uploads (PDFs, images, palette docs, voice docs).
* ``brand_text_chunks`` — text embeddings (Azure ``text-embedding-3-large``,
  3072 dims) with a HNSW cosine index.
* ``brand_image_chunks`` — aesthetic / reference image embeddings (CLIP
  ViT-B/32, 512 dims) with a HNSW cosine index.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "e5b7f4d18a29"
down_revision: Union[str, None] = "d92f3a1e6c47"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIP_DIM = 512
TEXT_EMBED_DIM = 3072


def upgrade() -> None:
    # --- Brand profile columns ------------------------------------------
    op.add_column("brands", sa.Column("logo_path", sa.String(length=512), nullable=True))
    op.add_column("brands", sa.Column("palette_dominant_hex", JSONB, nullable=True))
    op.add_column("brands", sa.Column("palette_accent_hex", JSONB, nullable=True))
    op.add_column("brands", sa.Column("typography", JSONB, nullable=True))
    op.add_column("brands", sa.Column("persona", sa.Text(), nullable=True))
    op.add_column("brands", sa.Column("competitors", JSONB, nullable=True))

    # --- brand_assets ---------------------------------------------------
    op.create_table(
        "brand_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("source_name", sa.String(length=255), nullable=False),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("media_type", sa.String(length=64), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brand_assets_brand_id"), "brand_assets", ["brand_id"], unique=False)
    op.create_index(op.f("ix_brand_assets_sha256"), "brand_assets", ["sha256"], unique=False)

    # --- brand_text_chunks ----------------------------------------------
    op.create_table(
        "brand_text_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("kind", sa.String(length=32), nullable=False, server_default="doc"),
        sa.Column("source", sa.String(length=255), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("embedding", Vector(TEXT_EMBED_DIM), nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["brand_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_brand_text_chunks_brand_id"), "brand_text_chunks", ["brand_id"], unique=False
    )
    op.create_index(
        op.f("ix_brand_text_chunks_asset_id"), "brand_text_chunks", ["asset_id"], unique=False
    )
    op.create_index(
        op.f("ix_brand_text_chunks_kind"), "brand_text_chunks", ["kind"], unique=False
    )
    # NOTE: no HNSW index on `embedding` — pgvector's HNSW is capped at 2000
    # dims and `text-embedding-3-large` is 3072-dim. For brand-scale corpora
    # (typically <10k chunks per brand) sequential cosine distance is fast
    # enough. If we outgrow this, options include: switching to `halfvec`
    # (4000-dim cap), truncating embeddings via Azure's `dimensions` param,
    # or moving to a dedicated vector store.

    # --- brand_image_chunks ---------------------------------------------
    op.create_table(
        "brand_image_chunks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("asset_id", sa.Integer(), nullable=True),
        sa.Column("image_path", sa.String(length=512), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("palette_hex", JSONB, nullable=True),
        sa.Column("embedding", Vector(CLIP_DIM), nullable=True),
        sa.Column("meta", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brands.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["asset_id"], ["brand_assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_brand_image_chunks_brand_id"), "brand_image_chunks", ["brand_id"], unique=False
    )
    op.create_index(
        op.f("ix_brand_image_chunks_asset_id"), "brand_image_chunks", ["asset_id"], unique=False
    )
    op.execute(
        "CREATE INDEX ix_brand_image_chunks_embedding_cosine "
        "ON brand_image_chunks USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_brand_image_chunks_embedding_cosine")
    op.drop_index(op.f("ix_brand_image_chunks_asset_id"), table_name="brand_image_chunks")
    op.drop_index(op.f("ix_brand_image_chunks_brand_id"), table_name="brand_image_chunks")
    op.drop_table("brand_image_chunks")

    op.execute("DROP INDEX IF EXISTS ix_brand_text_chunks_embedding_cosine")
    op.drop_index(op.f("ix_brand_text_chunks_kind"), table_name="brand_text_chunks")
    op.drop_index(op.f("ix_brand_text_chunks_asset_id"), table_name="brand_text_chunks")
    op.drop_index(op.f("ix_brand_text_chunks_brand_id"), table_name="brand_text_chunks")
    op.drop_table("brand_text_chunks")

    op.drop_index(op.f("ix_brand_assets_sha256"), table_name="brand_assets")
    op.drop_index(op.f("ix_brand_assets_brand_id"), table_name="brand_assets")
    op.drop_table("brand_assets")

    op.drop_column("brands", "competitors")
    op.drop_column("brands", "persona")
    op.drop_column("brands", "typography")
    op.drop_column("brands", "palette_accent_hex")
    op.drop_column("brands", "palette_dominant_hex")
    op.drop_column("brands", "logo_path")
