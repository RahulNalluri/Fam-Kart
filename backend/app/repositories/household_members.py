from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.household_member import HouseholdMember, HouseholdRole


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
