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

    def delete(self, membership: HouseholdMember) -> None:
        self.db.delete(membership)
        self.db.commit()

    def lock_for_ownership_transfer(
        self,
        *,
        household_id: UUID,
        current_owner_user_id: UUID,
        new_owner_user_id: UUID,
    ) -> tuple[HouseholdMember | None, HouseholdMember | None]:
        statement = (
            select(HouseholdMember)
            .where(
                HouseholdMember.household_id == household_id,
                HouseholdMember.user_id.in_(
                    [current_owner_user_id, new_owner_user_id],
                ),
            )
            .order_by(HouseholdMember.user_id.asc())
            .with_for_update()
        )
        memberships = self.db.execute(statement).scalars().all()
        memberships_by_user_id = {
            membership.user_id: membership for membership in memberships
        }
        return (
            memberships_by_user_id.get(current_owner_user_id),
            memberships_by_user_id.get(new_owner_user_id),
        )

    def transfer_ownership(
        self,
        *,
        current_owner: HouseholdMember,
        new_owner: HouseholdMember,
    ) -> None:
        current_owner.role = HouseholdRole.MEMBER
        new_owner.role = HouseholdRole.OWNER
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
