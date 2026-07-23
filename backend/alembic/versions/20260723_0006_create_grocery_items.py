"""Create grocery items.

Revision ID: 20260723_0006
Revises: 20260721_0005
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260723_0006"
down_revision: str | None = "20260721_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    grocery_item_status = postgresql.ENUM(
        "pending",
        "completed",
        name="grocery_item_status",
        create_type=False,
    )
    grocery_item_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "grocery_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("shopping_session_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "status",
            grocery_item_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_user_id", sa.Uuid(), nullable=True),
        sa.Column("completed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "length(trim(name)) > 0",
            name=op.f("ck_grocery_items_name_not_blank"),
        ),
        sa.CheckConstraint(
            "quantity IS NULL OR quantity > 0",
            name=op.f("ck_grocery_items_quantity_positive"),
        ),
        sa.CheckConstraint(
            "(status = 'pending' AND completed_at IS NULL) OR "
            "(status = 'completed' AND completed_at IS NOT NULL)",
            name=op.f("ck_grocery_items_status_completion_consistent"),
        ),
        sa.ForeignKeyConstraint(
            ["shopping_session_id"],
            ["shopping_sessions.id"],
            name=op.f("fk_grocery_items_shopping_session_id_shopping_sessions"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_grocery_items_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_to_user_id"],
            ["users.id"],
            name=op.f("fk_grocery_items_assigned_to_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["completed_by_user_id"],
            ["users.id"],
            name=op.f("fk_grocery_items_completed_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grocery_items")),
    )
    op.create_index(
        op.f("ix_grocery_items_created_by_user_id"),
        "grocery_items",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_items_assigned_to_user_id"),
        "grocery_items",
        ["assigned_to_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_items_completed_by_user_id"),
        "grocery_items",
        ["completed_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_grocery_items_shopping_session_id_status",
        "grocery_items",
        ["shopping_session_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_grocery_items_shopping_session_id_status",
        table_name="grocery_items",
    )
    op.drop_index(
        op.f("ix_grocery_items_completed_by_user_id"),
        table_name="grocery_items",
    )
    op.drop_index(
        op.f("ix_grocery_items_assigned_to_user_id"),
        table_name="grocery_items",
    )
    op.drop_index(
        op.f("ix_grocery_items_created_by_user_id"),
        table_name="grocery_items",
    )
    op.drop_table("grocery_items")

    grocery_item_status = postgresql.ENUM(
        "pending",
        "completed",
        name="grocery_item_status",
        create_type=False,
    )
    grocery_item_status.drop(op.get_bind(), checkfirst=True)
