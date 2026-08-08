"""Create push device registrations.

Revision ID: 20260808_0011
Revises: 20260807_0010
Create Date: 2026-08-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260808_0011"
down_revision: str | None = "20260807_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    push_platform = sa.Enum("android", "ios", name="push_platform")
    push_platform.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("installation_id", sa.Uuid(), nullable=False),
        sa.Column("expo_push_token", sa.String(length=255), nullable=False),
        sa.Column("platform", push_platform, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column(
            "last_registered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_push_devices_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_push_devices")),
    )
    op.create_index(op.f("ix_push_devices_user_id"), "push_devices", ["user_id"])
    op.create_index(
        op.f("ix_push_devices_installation_id"),
        "push_devices",
        ["installation_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_push_devices_expo_push_token"),
        "push_devices",
        ["expo_push_token"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_push_devices_expo_push_token"), table_name="push_devices")
    op.drop_index(op.f("ix_push_devices_installation_id"), table_name="push_devices")
    op.drop_index(op.f("ix_push_devices_user_id"), table_name="push_devices")
    op.drop_table("push_devices")
    sa.Enum(name="push_platform").drop(op.get_bind(), checkfirst=True)
