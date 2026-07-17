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
def user(db_session: Session) -> User:
    profile = User(
        email="update-profile@example.com",
        display_name="Original Name",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
    )
    db_session.add(profile)
    db_session.commit()
    db_session.refresh(profile)
    return profile


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


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_update_profile_changes_and_persists_allowed_fields(
    client: TestClient,
    db_session: Session,
    user: User,
) -> None:
    response = client.patch(
        "/api/v1/users/me",
        headers=authorization_header(user),
        json={"display_name": "  Rahul Nalluri  ", "preferred_language": "te"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Rahul Nalluri"
    assert response.json()["preferred_language"] == "te"
    assert response.json()["email"] == "update-profile@example.com"
    assert "password_hash" not in response.json()

    db_session.expire_all()
    saved_user = db_session.get(User, user.id)
    assert saved_user is not None
    assert saved_user.display_name == "Rahul Nalluri"
    assert saved_user.preferred_language == "te"


def test_update_profile_changes_one_field_without_resetting_the_other(
    client: TestClient,
    user: User,
) -> None:
    response = client.patch(
        "/api/v1/users/me",
        headers=authorization_header(user),
        json={"preferred_language": "te"},
    )

    assert response.status_code == 200
    assert response.json()["display_name"] == "Original Name"
    assert response.json()["preferred_language"] == "te"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"display_name": "   "},
        {"preferred_language": "fr"},
        {"email": "changed@example.com"},
        {"password": "replacement-password"},
    ],
)
def test_update_profile_rejects_invalid_or_restricted_fields(
    client: TestClient,
    user: User,
    payload: dict[str, str],
) -> None:
    response = client.patch(
        "/api/v1/users/me",
        headers=authorization_header(user),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_update_profile_requires_access_token(client: TestClient) -> None:
    response = client.patch(
        "/api/v1/users/me",
        json={"display_name": "Unauthorized Change"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
