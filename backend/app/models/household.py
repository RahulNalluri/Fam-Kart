from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.household_invitation import HouseholdInvitation
    from app.models.household_member import HouseholdMember


class Household(Base):
    __tablename__ = "households"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
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

    members: Mapped[list["HouseholdMember"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )
    invitations: Mapped[list["HouseholdInvitation"]] = relationship(
        back_populates="household",
        cascade="all, delete-orphan",
    )
