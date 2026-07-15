from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import verify_password
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


def registration_payload() -> dict[str, str]:
    return {
        "email": "Rahul@Example.com",
        "display_name": "  Rahul  ",
        "password": "familykart123",
        "preferred_language": "te",
    }


def test_register_user_returns_safe_profile(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post("/api/v1/auth/register", json=registration_payload())

    assert response.status_code == 201
    assert response.json()["email"] == "rahul@example.com"
    assert response.json()["display_name"] == "Rahul"
    assert response.json()["preferred_language"] == "te"
    assert response.json()["is_active"] is True
    assert "password" not in response.json()
    assert "password_hash" not in response.json()

    user = db_session.execute(select(User)).scalar_one()
    assert user.password_hash != "familykart123"
    assert verify_password("familykart123", user.password_hash) is True


def test_register_user_rejects_duplicate_email(client: TestClient) -> None:
    first_response = client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )
    duplicate_response = client.post(
        "/api/v1/auth/register",
        json=registration_payload(),
    )

    assert first_response.status_code == 201
    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["error"]["code"] == "http_409"
    assert duplicate_response.json()["error"]["message"] == (
        "An account with this email already exists."
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("email", "not-an-email"),
        ("display_name", "   "),
        ("password", "short"),
        ("preferred_language", "fr"),
    ],
)
def test_register_user_rejects_invalid_input(
    client: TestClient,
    field: str,
    value: str,
) -> None:
    payload = registration_payload()
    payload[field] = value

    response = client.post("/api/v1/auth/register", json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
