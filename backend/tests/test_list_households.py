from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.household import Household
from app.models.household_member import HouseholdMember, HouseholdRole
from app.models.user import User


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)
    with test_session() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_user(db_session: Session, *, email: str) -> User:
    user = User(
        email=email,
        display_name="Household List User",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_household_membership(
    db_session: Session,
    *,
    name: str,
    user: User,
    role: HouseholdRole,
) -> Household:
    household = Household(name=name)
    db_session.add(household)
    db_session.flush()
    db_session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role=role,
        ),
    )
    db_session.commit()
    db_session.refresh(household)
    return household


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_list_households_returns_only_current_users_memberships(
    client: TestClient,
    db_session: Session,
) -> None:
    current_user = create_user(db_session, email="current@example.com")
    other_user = create_user(db_session, email="other@example.com")
    zulu_household = create_household_membership(
        db_session,
        name="Zulu Family",
        user=current_user,
        role=HouseholdRole.MEMBER,
    )
    alpha_household = create_household_membership(
        db_session,
        name="Alpha Family",
        user=current_user,
        role=HouseholdRole.OWNER,
    )
    create_household_membership(
        db_session,
        name="Private Family",
        user=other_user,
        role=HouseholdRole.OWNER,
    )

    response = client.get(
        "/api/v1/households",
        headers=authorization_header(current_user),
    )

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == [
        "Alpha Family",
        "Zulu Family",
    ]
    assert response.json()[0]["id"] == str(alpha_household.id)
    assert response.json()[0]["role"] == "owner"
    assert response.json()[1]["id"] == str(zulu_household.id)
    assert response.json()[1]["role"] == "member"
    assert all("joined_at" in item for item in response.json())
    assert all("Private Family" != item["name"] for item in response.json())


def test_list_households_returns_empty_list_for_user_without_memberships(
    client: TestClient,
    db_session: Session,
) -> None:
    current_user = create_user(db_session, email="empty@example.com")

    response = client.get(
        "/api/v1/households",
        headers=authorization_header(current_user),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_list_households_requires_access_token(client: TestClient) -> None:
    response = client.get("/api/v1/households")

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
