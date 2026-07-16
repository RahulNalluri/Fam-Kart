from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import TokenType, decode_token, hash_password
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
        email="rahul@gmail.com",
        display_name="Rahul",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def login_payload() -> dict[str, str]:
    return {
        "email": "Rahul@Gmail.com",
        "password": "familykart123",
    }


def test_login_returns_access_and_refresh_tokens(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session)

    response = client.post("/api/v1/auth/login", json=login_payload())

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token_expires_in"] == 900
    assert body["refresh_token_expires_in"] == 2_592_000
    assert (
        decode_token(
            body["access_token"],
            expected_type=TokenType.ACCESS,
        ).subject
        == user.id
    )
    assert (
        decode_token(
            body["refresh_token"],
            expected_type=TokenType.REFRESH,
        ).subject
        == user.id
    )


@pytest.mark.parametrize("account_state", ["unknown", "wrong_password", "inactive"])
def test_login_rejects_invalid_credentials_consistently(
    client: TestClient,
    db_session: Session,
    account_state: str,
) -> None:
    payload = login_payload()
    if account_state != "unknown":
        create_user(db_session, is_active=account_state != "inactive")
    if account_state == "wrong_password":
        payload["password"] = "incorrect-password"

    response = client.post("/api/v1/auth/login", json=payload)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "http_401"
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_login_rejects_invalid_request(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "not-an-email", "password": ""},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
