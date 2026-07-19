from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models.household_member import HouseholdMember, HouseholdRole
from app.models.user import User


@dataclass(frozen=True)
class HouseholdMemberRecord:
    user_id: UUID
    display_name: str
    preferred_language: str
    role: HouseholdRole
    joined_at: datetime


class HouseholdMemberRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def user_owns_household(self, user_id: UUID) -> bool:
        statement = (
            select(HouseholdMember.id)
            .where(
                HouseholdMember.user_id == user_id,
                HouseholdMember.role == HouseholdRole.OWNER,
            )
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none() is not None

    def get_for_user_and_household(
        self,
        *,
        user_id: UUID,
        household_id: UUID,
    ) -> HouseholdMember | None:
        statement = select(HouseholdMember).where(
            HouseholdMember.user_id == user_id,
            HouseholdMember.household_id == household_id,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_for_household(self, household_id: UUID) -> list[HouseholdMemberRecord]:
        statement = (
            select(
                User.id,
                User.display_name,
                User.preferred_language,
                HouseholdMember.role,
                HouseholdMember.joined_at,
            )
            .join(User, User.id == HouseholdMember.user_id)
            .where(HouseholdMember.household_id == household_id)
            .order_by(
                case((HouseholdMember.role == HouseholdRole.OWNER, 0), else_=1),
                HouseholdMember.joined_at.asc(),
                User.id.asc(),
            )
        )
        rows = self.db.execute(statement).all()
        return [
            HouseholdMemberRecord(
                user_id=user_id,
                display_name=display_name,
                preferred_language=preferred_language,
                role=role,
                joined_at=joined_at,
            )
            for user_id, display_name, preferred_language, role, joined_at in rows
        ]
