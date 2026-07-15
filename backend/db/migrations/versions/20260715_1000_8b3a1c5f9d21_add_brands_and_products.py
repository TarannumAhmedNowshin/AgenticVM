"""add brands and products (pgvector CLIP embeddings)

Revision ID: 8b3a1c5f9d21
Revises: 2f2073f4a471
Create Date: 2026-07-15 10:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = "8b3a1c5f9d21"
down_revision: Union[str, None] = "2f2073f4a471"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CLIP_DIM = 512


def upgrade() -> None:
    # pgvector is enabled manually during setup; make this migration idempotent
    # in case a fresh environment forgot the CREATE EXTENSION step.
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "brands",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("voice", sa.Text(), nullable=True),
        sa.Column("guardrails", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brands_slug"), "brands", ["slug"], unique=True)

    op.create_table(
        "products",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("sku", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("price", sa.String(length=32), nullable=True),
        sa.Column("image_path", sa.String(length=512), nullable=True),
        sa.Column("embedding", Vector(CLIP_DIM), nullable=True),
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
        sa.UniqueConstraint("brand_id", "sku", name="uq_products_brand_sku"),
    )
    op.create_index(op.f("ix_products_brand_id"), "products", ["brand_id"], unique=False)
    op.create_index(op.f("ix_products_sku"), "products", ["sku"], unique=False)

    # IVFFlat cosine index on CLIP embeddings.
    # `lists = 100` is a reasonable default for catalogues up to ~100k rows.
    op.execute(
        "CREATE INDEX ix_products_embedding_cosine "
        "ON products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_embedding_cosine")
    op.drop_index(op.f("ix_products_sku"), table_name="products")
    op.drop_index(op.f("ix_products_brand_id"), table_name="products")
    op.drop_table("products")
    op.drop_index(op.f("ix_brands_slug"), table_name="brands")
    op.drop_table("brands")
