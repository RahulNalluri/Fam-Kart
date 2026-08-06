"""Create grocery mutation idempotency records.

Revision ID: 20260807_0010
Revises: 20260802_0009
Create Date: 2026-08-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260807_0010"
down_revision: str | None = "20260802_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "grocery_mutation_idempotency",
        sa.Column("mutation_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("shopping_session_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=16), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("response_status", sa.Integer(), nullable=False),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "operation IN ('add', 'edit', 'complete', 'reopen', 'delete')",
            name=op.f("ck_grocery_mutation_idempotency_operation_supported"),
        ),
        sa.CheckConstraint(
            "length(request_hash) = 64",
            name=op.f("ck_grocery_mutation_idempotency_request_hash_length"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_grocery_mutation_idempotency_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shopping_session_id"],
            ["shopping_sessions.id"],
            name=op.f(
                "fk_grocery_mutation_idempotency_shopping_session_id_shopping_sessions"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_grocery_mutation_idempotency_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "mutation_id",
            name=op.f("pk_grocery_mutation_idempotency"),
        ),
    )
    op.create_index(
        "ix_grocery_mutation_idempotency_household_created_at",
        "grocery_mutation_idempotency",
        ["household_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_mutation_idempotency_shopping_session_id"),
        "grocery_mutation_idempotency",
        ["shopping_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_mutation_idempotency_user_id"),
        "grocery_mutation_idempotency",
        ["user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_grocery_mutation_idempotency_user_id"),
        table_name="grocery_mutation_idempotency",
    )
    op.drop_index(
        op.f("ix_grocery_mutation_idempotency_shopping_session_id"),
        table_name="grocery_mutation_idempotency",
    )
    op.drop_index(
        "ix_grocery_mutation_idempotency_household_created_at",
        table_name="grocery_mutation_idempotency",
    )
    op.drop_table("grocery_mutation_idempotency")
