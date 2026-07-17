from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_refresh_token, hash_password, hash_refresh_token
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


def create_user(db_session: Session, *, is_active: bool = True) -> User:
    user = User(
        email="refresh@example.com",
        display_name="Refresh Test",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login(client: TestClient) -> dict[str, object]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "refresh@example.com", "password": "familykart123"},
    )
    assert response.status_code == 200
    return response.json()


def test_refresh_rotates_session_and_rejects_old_token(
    client: TestClient,
    db_session: Session,
) -> None:
    create_user(db_session)
    login_tokens = login(client)
    old_refresh_token = str(login_tokens["refresh_token"])

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert response.status_code == 200
    new_refresh_token = response.json()["refresh_token"]
    assert new_refresh_token != old_refresh_token
    sessions = db_session.scalars(
        select(AuthSession).order_by(AuthSession.created_at),
    ).all()
    assert len(sessions) == 2
    assert sessions[0].revoked_at is not None
    assert sessions[1].revoked_at is None
    assert sessions[1].refresh_token_hash == hash_refresh_token(new_refresh_token)

    reused = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": old_refresh_token},
    )

    assert reused.status_code == 401
    assert reused.json()["error"]["message"] == ("Invalid or expired refresh token.")
    assert len(db_session.scalars(select(AuthSession)).all()) == 2


def test_refresh_rejects_untracked_token(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    untracked_token = create_refresh_token(user.id)

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": untracked_token},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_refresh_rejects_inactive_user(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)
    tokens = login(client)
    user.is_active = False
    db_session.commit()

    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("refresh_token", ["not-a-jwt", ""])
def test_refresh_rejects_invalid_input(
    client: TestClient,
    refresh_token: str,
) -> None:
    response = client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )

    assert response.status_code in {401, 422}
