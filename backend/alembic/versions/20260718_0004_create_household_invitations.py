"""Create household invitations.

Revision ID: 20260718_0004
Revises: 20260716_0003
Create Date: 2026-07-18
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260718_0004"
down_revision: str | None = "20260716_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "household_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_household_invitations_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_household_invitations_created_by_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["used_by_user_id"],
            ["users.id"],
            name=op.f("fk_household_invitations_used_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household_invitations")),
    )
    op.create_index(
        op.f("ix_household_invitations_household_id"),
        "household_invitations",
        ["household_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_household_invitations_created_by_user_id"),
        "household_invitations",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_household_invitations_code_hash"),
        "household_invitations",
        ["code_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_household_invitations_code_hash"),
        table_name="household_invitations",
    )
    op.drop_index(
        op.f("ix_household_invitations_created_by_user_id"),
        table_name="household_invitations",
    )
    op.drop_index(
        op.f("ix_household_invitations_household_id"),
        table_name="household_invitations",
    )
    op.drop_table("household_invitations")
