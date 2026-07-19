from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.household import Household
from app.models.household_member import HouseholdMember, HouseholdRole


@dataclass(frozen=True)
class HouseholdMembershipRecord:
    household: Household
    role: HouseholdRole
    joined_at: datetime


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

    def list_for_user(self, user_id: UUID) -> list[HouseholdMembershipRecord]:
        statement = (
            select(
                Household,
                HouseholdMember.role,
                HouseholdMember.joined_at,
            )
            .join(
                HouseholdMember,
                HouseholdMember.household_id == Household.id,
            )
            .where(HouseholdMember.user_id == user_id)
            .order_by(Household.name.asc(), Household.id.asc())
        )
        rows = self.db.execute(statement).all()
        return [
            HouseholdMembershipRecord(
                household=household,
                role=role,
                joined_at=joined_at,
            )
            for household, role, joined_at in rows
        ]

    def get_for_user(
        self,
        *,
        household_id: UUID,
        user_id: UUID,
    ) -> HouseholdMembershipRecord | None:
        statement = (
            select(
                Household,
                HouseholdMember.role,
                HouseholdMember.joined_at,
            )
            .join(
                HouseholdMember,
                HouseholdMember.household_id == Household.id,
            )
            .where(
                Household.id == household_id,
                HouseholdMember.user_id == user_id,
            )
        )
        row = self.db.execute(statement).one_or_none()
        if row is None:
            return None

        household, role, joined_at = row
        return HouseholdMembershipRecord(
            household=household,
            role=role,
            joined_at=joined_at,
        )
