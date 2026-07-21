"""Create shopping sessions.

Revision ID: 20260721_0005
Revises: 20260718_0004
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260721_0005"
down_revision: str | None = "20260718_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    shopping_session_status = postgresql.ENUM(
        "active",
        "completed",
        name="shopping_session_status",
        create_type=False,
    )
    shopping_session_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "shopping_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "status",
            shopping_session_status,
            server_default="active",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_shopping_sessions_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_shopping_sessions_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_shopping_sessions")),
    )
    op.create_index(
        op.f("ix_shopping_sessions_created_by_user_id"),
        "shopping_sessions",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_shopping_sessions_household_id_status",
        "shopping_sessions",
        ["household_id", "status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_shopping_sessions_household_id_status",
        table_name="shopping_sessions",
    )
    op.drop_index(
        op.f("ix_shopping_sessions_created_by_user_id"),
        table_name="shopping_sessions",
    )
    op.drop_table("shopping_sessions")

    shopping_session_status = postgresql.ENUM(
        "active",
        "completed",
        name="shopping_session_status",
        create_type=False,
    )
    shopping_session_status.drop(op.get_bind(), checkfirst=True)
