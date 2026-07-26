"""Create grocery activity events.

Revision ID: 20260726_0007
Revises: 20260723_0006
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260726_0007"
down_revision: str | None = "20260723_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    grocery_activity_type = postgresql.ENUM(
        "item_added",
        "item_edited",
        "item_completed",
        "item_reopened",
        "item_deleted",
        name="grocery_activity_type",
        create_type=False,
    )
    grocery_activity_type.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "grocery_activity_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("household_id", sa.Uuid(), nullable=False),
        sa.Column("shopping_session_id", sa.Uuid(), nullable=False),
        sa.Column("grocery_item_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", grocery_activity_type, nullable=False),
        sa.Column("item_name", sa.String(length=160), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(item_name)) > 0",
            name=op.f("ck_grocery_activity_events_item_name_not_blank"),
        ),
        sa.CheckConstraint(
            "sequence_number > 0",
            name=op.f("ck_grocery_activity_events_sequence_number_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["household_id"],
            ["households.id"],
            name=op.f("fk_grocery_activity_events_household_id_households"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["shopping_session_id"],
            ["shopping_sessions.id"],
            name=op.f(
                "fk_grocery_activity_events_shopping_session_id_shopping_sessions"
            ),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"],
            ["users.id"],
            name=op.f("fk_grocery_activity_events_actor_user_id_users"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_grocery_activity_events")),
        sa.UniqueConstraint(
            "shopping_session_id",
            "sequence_number",
            name="uq_grocery_activity_events_session_sequence",
        ),
    )
    op.create_index(
        op.f("ix_grocery_activity_events_grocery_item_id"),
        "grocery_activity_events",
        ["grocery_item_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_grocery_activity_events_actor_user_id"),
        "grocery_activity_events",
        ["actor_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_grocery_activity_events_household_id_created_at",
        "grocery_activity_events",
        ["household_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_grocery_activity_events_session_id_created_at",
        "grocery_activity_events",
        ["shopping_session_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_grocery_activity_events_session_id_created_at",
        table_name="grocery_activity_events",
    )
    op.drop_index(
        "ix_grocery_activity_events_household_id_created_at",
        table_name="grocery_activity_events",
    )
    op.drop_index(
        op.f("ix_grocery_activity_events_actor_user_id"),
        table_name="grocery_activity_events",
    )
    op.drop_index(
        op.f("ix_grocery_activity_events_grocery_item_id"),
        table_name="grocery_activity_events",
    )
    op.drop_table("grocery_activity_events")

    grocery_activity_type = postgresql.ENUM(
        "item_added",
        "item_edited",
        "item_completed",
        "item_reopened",
        "item_deleted",
        name="grocery_activity_type",
        create_type=False,
    )
    grocery_activity_type.drop(op.get_bind(), checkfirst=True)
