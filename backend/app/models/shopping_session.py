from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Index, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.grocery_item import GroceryItem
    from app.models.household import Household


class ShoppingSessionStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"


class ShoppingSession(Base):
    __tablename__ = "shopping_sessions"
    __table_args__ = (
        Index(
            "ix_shopping_sessions_household_id_status",
            "household_id",
            "status",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[ShoppingSessionStatus] = mapped_column(
        Enum(
            ShoppingSessionStatus,
            name="shopping_session_status",
            values_callable=lambda statuses: [status.value for status in statuses],
        ),
        default=ShoppingSessionStatus.ACTIVE,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    household: Mapped["Household"] = relationship(back_populates="shopping_sessions")
    items: Mapped[list["GroceryItem"]] = relationship(
        back_populates="shopping_session",
        cascade="all, delete-orphan",
    )
