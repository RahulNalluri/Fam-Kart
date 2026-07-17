from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth_session import AuthSession
from app.models.household import Household
from app.models.household_member import HouseholdMember, HouseholdRole
from app.models.user import User

PASSWORD = "familykart123"
EMAIL = "delete-account@example.com"


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


def create_user(db_session: Session) -> User:
    user = User(
        email=EMAIL,
        display_name="Delete Account",
        password_hash=hash_password(PASSWORD),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def add_household_membership(
    db_session: Session,
    user: User,
    *,
    role: HouseholdRole,
) -> Household:
    household = Household(name="Deletion Test Family")
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


def login(client: TestClient) -> dict[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    assert response.status_code == 200
    return response.json()


def access_header(tokens: dict[str, str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def test_delete_account_removes_user_membership_and_sessions(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    household = add_household_membership(
        db_session,
        user,
        role=HouseholdRole.MEMBER,
    )
    tokens = login(client)

    response = client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=access_header(tokens),
        json={"password": PASSWORD},
    )

    assert response.status_code == 204
    assert response.content == b""
    assert db_session.get(User, user.id) is None
    assert db_session.scalar(select(AuthSession)) is None
    assert db_session.scalar(select(HouseholdMember)) is None
    assert db_session.get(Household, household.id) is not None

    profile_response = client.get(
        "/api/v1/users/me",
        headers=access_header(tokens),
    )
    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
    )
    assert profile_response.status_code == 401
    assert refresh_response.status_code == 401
    assert login_response.status_code == 401


def test_delete_account_rejects_incorrect_password(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    tokens = login(client)

    response = client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=access_header(tokens),
        json={"password": "incorrect-password"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Password confirmation is incorrect."
    )
    assert db_session.get(User, user.id) is not None
    assert db_session.scalar(select(AuthSession)) is not None


def test_delete_account_blocks_household_owner(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    add_household_membership(db_session, user, role=HouseholdRole.OWNER)
    tokens = login(client)

    response = client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=access_header(tokens),
        json={"password": PASSWORD},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "Transfer household ownership before deleting your account."
    )
    assert db_session.get(User, user.id) is not None


def test_delete_account_requires_access_token(client: TestClient) -> None:
    response = client.request(
        "DELETE",
        "/api/v1/users/me",
        json={"password": PASSWORD},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"password": ""},
        {"password": PASSWORD, "user_id": "another-user"},
    ],
)
def test_delete_account_rejects_invalid_request(
    client: TestClient,
    db_session: Session,
    payload: dict[str, str],
) -> None:
    user = create_user(db_session)
    tokens = login(client)

    response = client.request(
        "DELETE",
        "/api/v1/users/me",
        headers=access_header(tokens),
        json=payload,
    )

    assert response.status_code == 422
    assert db_session.get(User, user.id) is not None
