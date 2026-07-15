"""add displays and analyses

Revision ID: d92f3a1e6c47
Revises: c4e0d7f2a8b3
Create Date: 2026-07-15 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "d92f3a1e6c47"
down_revision: Union[str, None] = "c4e0d7f2a8b3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "displays",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("image_path", sa.String(length=512), nullable=False),
        sa.Column("image_sha256", sa.String(length=64), nullable=False),
        sa.Column("media_type", sa.String(length=64), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=True),
        sa.Column("height_px", sa.Integer(), nullable=True),
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
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_displays_brand_id"), "displays", ["brand_id"], unique=False)
    op.create_index(op.f("ix_displays_user_id"), "displays", ["user_id"], unique=False)
    op.create_index(op.f("ix_displays_image_sha256"), "displays", ["image_sha256"], unique=False)

    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("display_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("scene_graph", JSONB, nullable=True),
        sa.Column("prompt_version", sa.String(length=32), nullable=True),
        sa.Column("model_id", sa.String(length=128), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["display_id"], ["displays.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_analyses_display_id"), "analyses", ["display_id"], unique=False)
    op.create_index(op.f("ix_analyses_status"), "analyses", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_analyses_status"), table_name="analyses")
    op.drop_index(op.f("ix_analyses_display_id"), table_name="analyses")
    op.drop_table("analyses")
    op.drop_index(op.f("ix_displays_image_sha256"), table_name="displays")
    op.drop_index(op.f("ix_displays_user_id"), table_name="displays")
    op.drop_index(op.f("ix_displays_brand_id"), table_name="displays")
    op.drop_table("displays")
