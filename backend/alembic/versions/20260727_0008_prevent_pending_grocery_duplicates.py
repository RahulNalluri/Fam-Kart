"""Prevent duplicate pending grocery items.

Revision ID: 20260727_0008
Revises: 20260726_0007
Create Date: 2026-07-27
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260727_0008"
down_revision: str | None = "20260726_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_grocery_items_session_pending_name"


def upgrade() -> None:
    op.create_index(
        INDEX_NAME,
        "grocery_items",
        ["shopping_session_id", sa.text("lower(trim(name))")],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="grocery_items")
