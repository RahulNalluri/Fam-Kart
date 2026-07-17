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
