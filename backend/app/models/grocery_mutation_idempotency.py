from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GroceryMutationIdempotency(Base):
    __tablename__ = "grocery_mutation_idempotency"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('add', 'edit', 'complete', 'reopen', 'delete')",
            name="operation_supported",
        ),
        CheckConstraint(
            "length(request_hash) = 64",
            name="request_hash_length",
        ),
        Index(
            "ix_grocery_mutation_idempotency_household_created_at",
            "household_id",
            "created_at",
        ),
    )

    mutation_id: Mapped[UUID] = mapped_column(primary_key=True)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    shopping_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    response_status: Mapped[int] = mapped_column(Integer, nullable=False)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
