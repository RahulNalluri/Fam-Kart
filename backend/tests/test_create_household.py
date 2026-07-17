from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
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
        display_name="Household Creator",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_create_household_assigns_creator_as_owner(
    client: TestClient,
    db_session: Session,
) -> None:
    creator = create_user(db_session, email="creator@example.com")
    other_user = create_user(db_session, email="other@example.com")

    response = client.post(
        "/api/v1/households",
        headers=authorization_header(creator),
        json={"name": "  Nalluri Family  "},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Nalluri Family"
    assert "id" in response.json()
    assert "created_at" in response.json()
    assert "updated_at" in response.json()

    household = db_session.scalar(select(Household))
    membership = db_session.scalar(select(HouseholdMember))
    assert household is not None
    assert str(household.id) == response.json()["id"]
    assert household.name == "Nalluri Family"
    assert membership is not None
    assert membership.household_id == household.id
    assert membership.user_id == creator.id
    assert membership.user_id != other_user.id
    assert membership.role == HouseholdRole.OWNER


def test_create_household_requires_access_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/households",
        json={"name": "Unauthorized Family"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "a" * 121},
        {"name": "Valid Family", "owner_id": "another-user"},
    ],
)
def test_create_household_rejects_invalid_input(
    client: TestClient,
    db_session: Session,
    payload: dict[str, str],
) -> None:
    creator = create_user(db_session, email="invalid-input@example.com")

    response = client.post(
        "/api/v1/households",
        headers=authorization_header(creator),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert db_session.scalar(select(Household)) is None
    assert db_session.scalar(select(HouseholdMember)) is None
