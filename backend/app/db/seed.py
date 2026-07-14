from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Environment
from app.models import Household, HouseholdMember, HouseholdRole, User

DEMO_USER_EMAIL = "demo@familykart.local"
DEMO_USER_NAME = "Demo User"
DEMO_HOUSEHOLD_NAME = "Demo Family"


@dataclass(frozen=True)
class SeedResult:
    users_created: int
    households_created: int
    memberships_created: int


def seed_development_data(
    db: Session,
    *,
    environment: Environment,
) -> SeedResult:
    if environment == "production":
        raise RuntimeError("Development seed data cannot be loaded in production.")

    users_created = 0
    households_created = 0
    memberships_created = 0

    try:
        user = db.scalar(
            select(User).where(User.email == DEMO_USER_EMAIL),
        )

        if user is None:
            user = User(
                email=DEMO_USER_EMAIL,
                display_name=DEMO_USER_NAME,
                preferred_language="en",
            )
            db.add(user)
            db.flush()
            users_created = 1

        household = db.scalar(
            select(Household)
            .join(HouseholdMember)
            .where(
                HouseholdMember.user_id == user.id,
                HouseholdMember.role == HouseholdRole.OWNER,
                Household.name == DEMO_HOUSEHOLD_NAME,
            ),
        )

        if household is None:
            household = Household(name=DEMO_HOUSEHOLD_NAME)
            db.add(household)
            db.flush()
            households_created = 1

            membership = HouseholdMember(
                household_id=household.id,
                user_id=user.id,
                role=HouseholdRole.OWNER,
            )
            db.add(membership)
            memberships_created = 1

        db.commit()
    except Exception:
        db.rollback()
        raise

    return SeedResult(
        users_created=users_created,
        households_created=households_created,
        memberships_created=memberships_created,
    )
