import asyncio
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from starlette.websockets import WebSocketDisconnect

from app.api.realtime import get_realtime_subscription_coordinator
from app.core.security import create_access_token, create_refresh_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Household, HouseholdMember, HouseholdRole, User
from app.schemas.realtime import (
    GroceryItemRealtimePayload,
    RealtimeCloseCode,
    RealtimeEventEnvelope,
    RealtimeEventType,
)
from app.services.realtime_connections import connection_manager
from app.services.realtime_subscription_coordinator import (
    RealtimeSubscriptionCoordinator,
    RealtimeSubscriptionStartError,
)


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
def subscription_coordinator() -> RealtimeSubscriptionCoordinator:
    coordinator = Mock(spec=RealtimeSubscriptionCoordinator)
    coordinator.acquire = AsyncMock()
    coordinator.release = AsyncMock()
    return coordinator


@pytest.fixture
def client(
    db_session: Session,
    subscription_coordinator: RealtimeSubscriptionCoordinator,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_realtime_subscription_coordinator] = (
        lambda: subscription_coordinator
    )
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


async def broadcast_after_registration(
    household_id: UUID,
    user_id: UUID,
    event: RealtimeEventEnvelope,
) -> int:
    for _ in range(100):
        if await connection_manager.connection_count(household_id, user_id) == 1:
            return await connection_manager.broadcast(household_id, event)
        await asyncio.sleep(0.001)
    raise AssertionError("WebSocket connection was not registered.")


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
    subscription_coordinator: RealtimeSubscriptionCoordinator,
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

    subscription_coordinator.acquire.assert_awaited_once_with(household.id)
    subscription_coordinator.release.assert_awaited_once_with(household.id)


def test_subscription_start_failure_closes_as_temporarily_unavailable(
    client: TestClient,
    db_session: Session,
    subscription_coordinator: RealtimeSubscriptionCoordinator,
) -> None:
    user = create_user(db_session, email="realtime-redis-unavailable@example.com")
    household = create_household(db_session, name="Redis Unavailable")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.MEMBER,
    )
    subscription_coordinator.acquire.side_effect = RealtimeSubscriptionStartError(
        "redis unavailable",
    )

    assert_connection_rejected(
        client,
        websocket_url(household.id),
        headers=authorization_header(create_access_token(user.id)),
        expected_code=RealtimeCloseCode.SERVICE_UNAVAILABLE,
        expected_reason="Real-time service unavailable.",
    )

    subscription_coordinator.release.assert_not_awaited()


def test_authenticated_connection_receives_local_household_broadcast(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="realtime-local-broadcast@example.com")
    household = create_household(db_session, name="Local Realtime Broadcast")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.MEMBER,
    )
    event = RealtimeEventEnvelope(
        event_id=uuid4(),
        event_type=RealtimeEventType.GROCERY_ITEM_ADDED,
        household_id=household.id,
        occurred_at=datetime.now(UTC),
        payload=GroceryItemRealtimePayload(
            shopping_session_id=uuid4(),
            grocery_item_id=uuid4(),
            actor_user_id=user.id,
            item_name="Milk",
            sequence_number=1,
        ),
    )

    with client.websocket_connect(
        websocket_url(household.id),
        headers=authorization_header(create_access_token(user.id)),
    ) as websocket:
        delivered = websocket.portal.call(
            broadcast_after_registration,
            household.id,
            user.id,
            event,
        )
        received = websocket.receive_json()

    assert delivered == 1
    assert received == event.model_dump(mode="json")


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
