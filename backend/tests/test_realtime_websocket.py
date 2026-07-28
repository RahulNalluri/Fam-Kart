from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.core.security import create_access_token, create_refresh_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Household, HouseholdMember, HouseholdRole, User
from app.schemas.realtime import RealtimeCloseCode


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
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


def create_user(
    db_session: Session,
    *,
    email: str,
    is_active: bool = True,
) -> User:
    user = User(
        email=email,
        display_name="Realtime WebSocket User",
        password_hash="!",
        preferred_language="en",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_household(db_session: Session, *, name: str) -> Household:
    household = Household(name=name)
    db_session.add(household)
    db_session.commit()
    db_session.refresh(household)
    return household


def add_membership(
    db_session: Session,
    *,
    household: Household,
    user: User,
    role: HouseholdRole,
) -> HouseholdMember:
    membership = HouseholdMember(
        household_id=household.id,
        user_id=user.id,
        role=role,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def websocket_url(household_id: object) -> str:
    return f"/api/v1/households/{household_id}/ws"


def authorization_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def assert_connection_rejected(
    client: TestClient,
    url: str,
    *,
    expected_code: RealtimeCloseCode,
    expected_reason: str,
    headers: dict[str, str] | None = None,
) -> None:
    with client.websocket_connect(url, headers=(headers or {}).copy()) as websocket:
        with pytest.raises(WebSocketDisconnect) as disconnected:
            websocket.receive_text()

    assert disconnected.value.code == expected_code
    assert disconnected.value.reason == expected_reason


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_household_member_can_connect_and_disconnect_cleanly(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
) -> None:
    user = create_user(
        db_session,
        email=f"realtime-connect-{role.value}@example.com",
    )
    household = create_household(db_session, name=f"Realtime {role.value}")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=role,
    )

    with client.websocket_connect(
        websocket_url(household.id),
        headers=authorization_header(create_access_token(user.id)),
    ) as websocket:
        websocket.send_text("connection remains open")


@pytest.mark.parametrize(
    "headers",
    [
        None,
        {"Authorization": "Basic credentials"},
        {"Authorization": "Bearer invalid"},
    ],
)
def test_missing_or_invalid_credentials_close_as_unauthorized(
    client: TestClient,
    headers: dict[str, str] | None,
) -> None:
    assert_connection_rejected(
        client,
        websocket_url(uuid4()),
        headers=headers,
        expected_code=RealtimeCloseCode.AUTHENTICATION_REQUIRED,
        expected_reason="Authentication required.",
    )


def test_expired_access_token_closes_as_unauthorized(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="realtime-expired@example.com")
    expired_token = create_access_token(
        user.id,
        now=datetime.now(UTC) - timedelta(minutes=16),
    )

    assert_connection_rejected(
        client,
        websocket_url(uuid4()),
        headers=authorization_header(expired_token),
        expected_code=RealtimeCloseCode.AUTHENTICATION_REQUIRED,
        expected_reason="Authentication required.",
    )


def test_refresh_token_closes_as_unauthorized(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="realtime-refresh@example.com")

    assert_connection_rejected(
        client,
        websocket_url(uuid4()),
        headers=authorization_header(create_refresh_token(user.id)),
        expected_code=RealtimeCloseCode.AUTHENTICATION_REQUIRED,
        expected_reason="Authentication required.",
    )


@pytest.mark.parametrize("user_state", ["missing", "inactive"])
def test_missing_or_inactive_user_closes_as_unauthorized(
    client: TestClient,
    db_session: Session,
    user_state: str,
) -> None:
    if user_state == "inactive":
        user_id = create_user(
            db_session,
            email="realtime-inactive@example.com",
            is_active=False,
        ).id
    else:
        user_id = uuid4()

    assert_connection_rejected(
        client,
        websocket_url(uuid4()),
        headers=authorization_header(create_access_token(user_id)),
        expected_code=RealtimeCloseCode.AUTHENTICATION_REQUIRED,
        expected_reason="Authentication required.",
    )


@pytest.mark.parametrize("household_state", ["unknown", "outsider"])
def test_unknown_or_inaccessible_household_uses_same_private_close(
    client: TestClient,
    db_session: Session,
    household_state: str,
) -> None:
    user = create_user(
        db_session,
        email=f"realtime-{household_state}@example.com",
    )
    household_id: UUID = (
        create_household(db_session, name="Hidden Realtime Household").id
        if household_state == "outsider"
        else uuid4()
    )

    assert_connection_rejected(
        client,
        websocket_url(household_id),
        headers=authorization_header(create_access_token(user.id)),
        expected_code=RealtimeCloseCode.HOUSEHOLD_NOT_FOUND,
        expected_reason="Household not found.",
    )


def test_removed_member_cannot_reconnect(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="realtime-removed@example.com")
    household = create_household(db_session, name="Removed Realtime Member")
    membership = add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.MEMBER,
    )
    db_session.delete(membership)
    db_session.commit()

    assert_connection_rejected(
        client,
        websocket_url(household.id),
        headers=authorization_header(create_access_token(user.id)),
        expected_code=RealtimeCloseCode.HOUSEHOLD_NOT_FOUND,
        expected_reason="Household not found.",
    )


def test_query_string_token_is_not_accepted(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="realtime-query-token@example.com")

    assert_connection_rejected(
        client,
        f"{websocket_url(uuid4())}?access_token={create_access_token(user.id)}",
        expected_code=RealtimeCloseCode.AUTHENTICATION_REQUIRED,
        expected_reason="Authentication required.",
    )


def test_malformed_household_id_uses_policy_violation_close(
    client: TestClient,
) -> None:
    with pytest.raises(WebSocketDisconnect) as disconnected:
        with client.websocket_connect(
            websocket_url("not-a-uuid"),
            headers=authorization_header(create_access_token(uuid4())),
        ):
            pass

    assert disconnected.value.code == 1008
