from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.household import Household


class HouseholdGroceryAlias(Base):
    __tablename__ = "household_grocery_aliases"
    __table_args__ = (
        CheckConstraint(
            "length(trim(alias)) > 0",
            name="alias_not_blank",
        ),
        CheckConstraint(
            "length(trim(normalized_alias)) > 0",
            name="normalized_alias_not_blank",
        ),
        CheckConstraint(
            "length(trim(canonical_key)) > 0",
            name="canonical_key_not_blank",
        ),
        UniqueConstraint(
            "household_id",
            "normalized_alias",
            name="uq_household_grocery_aliases_household_normalized_alias",
        ),
        Index(
            "ix_household_grocery_aliases_household_canonical_key",
            "household_id",
            "canonical_key",
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    household_id: Mapped[UUID] = mapped_column(
        ForeignKey("households.id", ondelete="CASCADE"),
        nullable=False,
    )
    alias: Mapped[str] = mapped_column(String(160), nullable=False)
    normalized_alias: Mapped[str] = mapped_column(String(160), nullable=False)
    canonical_key: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    household: Mapped["Household"] = relationship(back_populates="grocery_aliases")
