from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class GroceryActivityType(StrEnum):
    ITEM_ADDED = "item_added"
    ITEM_EDITED = "item_edited"
    ITEM_COMPLETED = "item_completed"
    ITEM_REOPENED = "item_reopened"
    ITEM_DELETED = "item_deleted"


class GroceryActivityEvent(Base):
    __tablename__ = "grocery_activity_events"
    __table_args__ = (
        CheckConstraint(
            "length(trim(item_name)) > 0",
            name="item_name_not_blank",
        ),
        CheckConstraint(
            "sequence_number > 0",
            name="sequence_number_positive",
        ),
        UniqueConstraint(
            "shopping_session_id",
            "sequence_number",
            name="uq_grocery_activity_events_session_sequence",
        ),
        Index(
            "ix_grocery_activity_events_household_id_created_at",
            "household_id",
            "created_at",
        ),
        Index(
            "ix_grocery_activity_events_session_id_created_at",
            "shopping_session_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    shopping_session_id: Mapped[UUID] = mapped_column(
        ForeignKey("shopping_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    grocery_item_id: Mapped[UUID] = mapped_column(nullable=False, index=True)
    actor_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[GroceryActivityType] = mapped_column(
        Enum(
            GroceryActivityType,
            name="grocery_activity_type",
            values_callable=lambda event_types: [
                event_type.value for event_type in event_types
            ],
        ),
        nullable=False,
    )
    item_name: Mapped[str] = mapped_column(String(160), nullable=False)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        server_default=func.now(),
        nullable=False,
    )
