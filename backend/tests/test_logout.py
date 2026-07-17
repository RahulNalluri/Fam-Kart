from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_refresh_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.auth_session import AuthSession
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


def create_user(db_session: Session) -> User:
    user = User(
        email="logout@example.com",
        display_name="Logout Test",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "logout@example.com", "password": "familykart123"},
    )
    assert response.status_code == 200
    return response.json()


def test_logout_revokes_session_and_blocks_refresh(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session)
    tokens = login(client)

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 204
    assert response.content == b""
    auth_session = db_session.scalar(select(AuthSession))
    assert auth_session is not None
    db_session.refresh(auth_session)
    assert auth_session.revoked_at is not None

    refresh_response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_response.status_code == 401


def test_repeated_logout_is_rejected(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session)
    tokens = login(client)
    payload = {"refresh_token": tokens["refresh_token"]}

    first_response = client.post("/api/v1/auth/logout", json=payload)
    second_response = client.post("/api/v1/auth/logout", json=payload)

    assert first_response.status_code == 204
    assert second_response.status_code == 401
    assert second_response.headers["www-authenticate"] == "Bearer"
    assert second_response.json()["error"]["message"] == (
        "Invalid or expired refresh token."
    )


@pytest.mark.parametrize("token_kind", ["malformed", "access", "untracked"])
def test_logout_rejects_invalid_tokens(
    client: TestClient,
    db_session: Session,
    token_kind: str,
) -> None:
    user = create_user(db_session)
    tokens = login(client)
    if token_kind == "malformed":
        token = "not-a-jwt"
    elif token_kind == "access":
        token = str(tokens["access_token"])
    else:
        token = create_refresh_token(user.id)

    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": token},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["message"] == ("Invalid or expired refresh token.")


def test_logout_rejects_empty_request(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": ""},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
