from collections.abc import Generator
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.push_device import PushDevice
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


def create_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        display_name="Push API User",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_authenticated_user_registers_updates_and_deactivates_device(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, "push-api@example.com")
    installation_id = uuid4()
    url = "/api/v1/users/me/push-devices"
    payload = {
        "installation_id": str(installation_id),
        "expo_push_token": "ExponentPushToken[api_token_123456789]",
        "platform": "android",
    }

    created = client.put(url, headers=headers(user), json=payload)
    assert created.status_code == 200
    assert created.json()["installation_id"] == str(installation_id)
    assert created.json()["platform"] == "android"
    assert "expo_push_token" not in created.json()

    payload["expo_push_token"] = "ExpoPushToken[rotated_api_token_123]"
    updated = client.put(url, headers=headers(user), json=payload)
    assert updated.status_code == 200
    assert updated.json()["id"] == created.json()["id"]

    removed = client.delete(f"{url}/{installation_id}", headers=headers(user))
    assert removed.status_code == 204
    device = db_session.get(PushDevice, UUID(created.json()["id"]))
    assert device is not None
    assert device.is_active is False


def test_push_device_routes_require_authentication(client: TestClient) -> None:
    installation_id = uuid4()
    response = client.put(
        "/api/v1/users/me/push-devices",
        json={
            "installation_id": str(installation_id),
            "expo_push_token": "ExpoPushToken[unauthorized_token_1]",
            "platform": "ios",
        },
    )
    assert response.status_code == 401

    response = client.delete(f"/api/v1/users/me/push-devices/{installation_id}")
    assert response.status_code == 401


@pytest.mark.parametrize(
    "field,value",
    [
        ("installation_id", "not-a-uuid"),
        ("expo_push_token", "ordinary-device-token"),
        ("platform", "web"),
    ],
)
def test_registration_rejects_invalid_device_data(
    client: TestClient,
    db_session: Session,
    field: str,
    value: str,
) -> None:
    user = create_user(db_session, f"push-invalid-{field}@example.com")
    payload = {
        "installation_id": str(uuid4()),
        "expo_push_token": "ExpoPushToken[valid_token_123456]",
        "platform": "android",
    }
    payload[field] = value

    response = client.put(
        "/api/v1/users/me/push-devices",
        headers=headers(user),
        json=payload,
    )
    assert response.status_code == 422


def test_deactivation_does_not_reveal_other_users_device(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, "push-api-owner@example.com")
    other = create_user(db_session, "push-api-other@example.com")
    installation_id = uuid4()
    client.put(
        "/api/v1/users/me/push-devices",
        headers=headers(owner),
        json={
            "installation_id": str(installation_id),
            "expo_push_token": "ExpoPushToken[private_token_12345]",
            "platform": "ios",
        },
    )

    response = client.delete(
        f"/api/v1/users/me/push-devices/{installation_id}",
        headers=headers(other),
    )
    assert response.status_code == 204
    assert db_session.query(PushDevice).one().is_active is True
