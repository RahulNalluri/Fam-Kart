from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
)
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
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_user(db_session: Session, *, is_active: bool = True) -> User:
    user = User(
        email="profile@example.com",
        display_name="Profile Test",
        password_hash=hash_password("familykart123"),
        preferred_language="te",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def authorization_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_current_user_returns_safe_personal_profile(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    token = create_access_token(user.id)

    response = client.get(
        "/api/v1/users/me",
        headers=authorization_header(token),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(user.id)
    assert response.json()["email"] == "profile@example.com"
    assert response.json()["display_name"] == "Profile Test"
    assert response.json()["preferred_language"] == "te"
    assert response.json()["is_active"] is True
    assert "password_hash" not in response.json()


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic credentials"},
        {"Authorization": "Bearer not-a-jwt"},
    ],
)
def test_current_user_rejects_missing_or_invalid_credentials(
    client: TestClient,
    headers: dict[str, str],
) -> None:
    response = client.get("/api/v1/users/me", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["message"] == ("Invalid or expired access token.")


def test_current_user_rejects_refresh_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)

    response = client.get(
        "/api/v1/users/me",
        headers=authorization_header(create_refresh_token(user.id)),
    )

    assert response.status_code == 401


def test_current_user_rejects_expired_access_token(client: TestClient) -> None:
    token = create_access_token(
        uuid4(),
        now=datetime.now(UTC) - timedelta(minutes=16),
    )

    response = client.get(
        "/api/v1/users/me",
        headers=authorization_header(token),
    )

    assert response.status_code == 401


def test_current_user_rejects_unknown_user(client: TestClient) -> None:
    response = client.get(
        "/api/v1/users/me",
        headers=authorization_header(create_access_token(uuid4())),
    )

    assert response.status_code == 401


def test_current_user_rejects_inactive_user(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, is_active=False)

    response = client.get(
        "/api/v1/users/me",
        headers=authorization_header(create_access_token(user.id)),
    )

    assert response.status_code == 401
