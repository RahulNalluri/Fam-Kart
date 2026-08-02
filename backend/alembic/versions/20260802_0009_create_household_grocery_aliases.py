"""Create household grocery aliases.

Revision ID: 20260802_0009
Revises: 20260727_0008
Create Date: 2026-08-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260802_0009"
down_revision: str | None = "20260727_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "household_grocery_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=160), nullable=False),
        sa.Column("normalized_alias", sa.String(length=160), nullable=False),
        sa.Column("canonical_key", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
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
        sa.CheckConstraint(
            "length(trim(alias)) > 0",
            name=op.f("ck_household_grocery_aliases_alias_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(normalized_alias)) > 0",
            name=op.f("ck_household_grocery_aliases_normalized_alias_not_blank"),
        ),
        sa.CheckConstraint(
            "length(trim(canonical_key)) > 0",
            name=op.f("ck_household_grocery_aliases_canonical_key_not_blank"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_household_grocery_aliases_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            name=op.f("fk_household_grocery_aliases_created_by_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_household_grocery_aliases")),
        sa.UniqueConstraint(
            "household_id",
            "normalized_alias",
            name="uq_household_grocery_aliases_household_normalized_alias",
        ),
    )
    op.create_index(
        op.f("ix_household_grocery_aliases_created_by_user_id"),
        "household_grocery_aliases",
        ["created_by_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_household_grocery_aliases_household_canonical_key",
        "household_grocery_aliases",
        ["household_id", "canonical_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_household_grocery_aliases_household_canonical_key",
        table_name="household_grocery_aliases",
    )
    op.drop_index(
        op.f("ix_household_grocery_aliases_created_by_user_id"),
        table_name="household_grocery_aliases",
    )
    op.drop_table("household_grocery_aliases")
