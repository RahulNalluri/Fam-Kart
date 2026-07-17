from uuid import UUID

from sqlalchemy.orm import Session

from app.models.household import Household
from app.models.household_member import HouseholdMember, HouseholdRole


class HouseholdRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_with_owner(self, *, name: str, owner_id: UUID) -> Household:
        household = Household(name=name)

        try:
            self.db.add(household)
            self.db.flush()
            self.db.add(
                HouseholdMember(
                    household_id=household.id,
                    user_id=owner_id,
                    role=HouseholdRole.OWNER,
                ),
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(household)
        return household
