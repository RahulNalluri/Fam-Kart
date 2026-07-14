from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.seed import seed_development_data
from app.models import Household, HouseholdMember, HouseholdRole, User


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        yield session

    Base.metadata.drop_all(engine)
    engine.dispose()


def test_seed_creates_development_data(db_session: Session) -> None:
    result = seed_development_data(
        db_session,
        environment="development",
    )

    assert result.users_created == 1
    assert result.households_created == 1
    assert result.memberships_created == 1

    user = db_session.scalar(select(User))
    household = db_session.scalar(select(Household))
    membership = db_session.scalar(select(HouseholdMember))

    assert user is not None
    assert user.email == "demo@familykart.local"
    assert user.display_name == "Demo User"
    assert user.preferred_language == "en"

    assert household is not None
    assert household.name == "Demo Family"

    assert membership is not None
    assert membership.user_id == user.id
    assert membership.household_id == household.id
    assert membership.role == HouseholdRole.OWNER


def test_seed_is_idempotent(db_session: Session) -> None:
    seed_development_data(
        db_session,
        environment="testing",
    )

    second_result = seed_development_data(
        db_session,
        environment="testing",
    )

    assert second_result.users_created == 0
    assert second_result.households_created == 0
    assert second_result.memberships_created == 0

    user_count = db_session.scalar(
        select(func.count()).select_from(User),
    )
    household_count = db_session.scalar(
        select(func.count()).select_from(Household),
    )
    membership_count = db_session.scalar(
        select(func.count()).select_from(HouseholdMember),
    )

    assert user_count == 1
    assert household_count == 1
    assert membership_count == 1


def test_seed_is_blocked_in_production(db_session: Session) -> None:
    with pytest.raises(
        RuntimeError,
        match="Development seed data cannot be loaded in production",
    ):
        seed_development_data(
            db_session,
            environment="production",
        )

    user_count = db_session.scalar(
        select(func.count()).select_from(User),
    )

    assert user_count == 0
