"""switch product embedding index from ivfflat to hnsw

Revision ID: c4e0d7f2a8b3
Revises: 8b3a1c5f9d21
Create Date: 2026-07-15 11:00:00.000000

`ivfflat` trains its centroids at index creation time, which is a bad fit for
a table that starts empty and gets seeded later. `hnsw` needs no training and
scales well from 30 rows to 100k+.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4e0d7f2a8b3"
down_revision: Union[str, None] = "8b3a1c5f9d21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_embedding_cosine")
    op.execute(
        "CREATE INDEX ix_products_embedding_cosine "
        "ON products USING hnsw (embedding vector_cosine_ops) "
        "WITH (m = 16, ef_construction = 64)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_embedding_cosine")
    op.execute(
        "CREATE INDEX ix_products_embedding_cosine "
        "ON products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
    )
