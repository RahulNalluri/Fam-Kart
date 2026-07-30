import asyncio
from collections.abc import Generator
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.security import create_access_token
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    GroceryActivityEvent,
    Household,
    HouseholdMember,
    HouseholdRole,
    ShoppingSession,
    User,
)
from app.schemas.realtime import RealtimeEventEnvelope, RealtimeEventType
from app.services.realtime_channels import household_event_channel

pytestmark = pytest.mark.redis_integration


def build_redis_client() -> Redis:
    return Redis.from_url(str(settings.redis_url), decode_responses=True)


async def require_household_subscriber(household_id: UUID) -> None:
    redis_client = build_redis_client()
    channel = household_event_channel(household_id)
    try:
        for _ in range(40):
            subscribers = await redis_client.pubsub_numsub(channel)
            if subscribers and int(subscribers[0][1]) == 1:
                return
            await asyncio.sleep(0.05)
    finally:
        await redis_client.aclose()

    raise AssertionError("Household Redis subscriber did not become ready.")


@pytest.fixture(scope="module", autouse=True)
def require_redis() -> None:
    async def ping() -> None:
        redis_client = build_redis_client()
        try:
            await redis_client.ping()
        except RedisError as error:
            pytest.skip(f"Redis integration server is unavailable: {error}")
        finally:
            await redis_client.aclose()

    asyncio.run(ping())


def test_grocery_api_mutation_reaches_all_household_websockets() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)

    with test_session() as db:
        owner = User(
            email="workflow-owner@example.com",
            display_name="Workflow Owner",
            password_hash="!",
            preferred_language="en",
        )
        member = User(
            email="workflow-member@example.com",
            display_name="Workflow Member",
            password_hash="!",
            preferred_language="te",
        )
        household = Household(name="Workflow Household")
        db.add_all((owner, member, household))
        db.flush()
        db.add_all(
            (
                HouseholdMember(
                    household_id=household.id,
                    user_id=owner.id,
                    role=HouseholdRole.OWNER,
                ),
                HouseholdMember(
                    household_id=household.id,
                    user_id=member.id,
                    role=HouseholdRole.MEMBER,
                ),
            ),
        )
        shopping_session = ShoppingSession(
            household_id=household.id,
            created_by_user_id=owner.id,
        )
        db.add(shopping_session)
        db.commit()
        owner_id = owner.id
        member_id = member.id
        household_id = household.id
        shopping_session_id = shopping_session.id

    def override_db() -> Generator[Session, None, None]:
        with test_session() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    collection_url = (
        f"/api/v1/households/{household_id}/shopping-sessions/"
        f"{shopping_session_id}/items"
    )
    websocket_url = f"/api/v1/households/{household_id}/ws"
    owner_headers = {
        "Authorization": f"Bearer {create_access_token(owner_id)}",
    }
    member_headers = {
        "Authorization": f"Bearer {create_access_token(member_id)}",
    }

    try:
        with TestClient(app) as client:
            with client.websocket_connect(
                websocket_url,
                headers=owner_headers,
            ) as owner_websocket:
                with client.websocket_connect(
                    websocket_url,
                    headers=member_headers,
                ) as member_websocket:
                    asyncio.run(require_household_subscriber(household_id))

                    response = client.post(
                        collection_url,
                        headers=owner_headers,
                        json={"name": "Milk", "quantity": "2", "unit": "packets"},
                    )

                    owner_event = RealtimeEventEnvelope.model_validate(
                        owner_websocket.receive_json(),
                    )
                    member_event = RealtimeEventEnvelope.model_validate(
                        member_websocket.receive_json(),
                    )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert owner_event == member_event
    assert owner_event.event_type == RealtimeEventType.GROCERY_ITEM_ADDED
    assert owner_event.household_id == household_id
    assert owner_event.payload.shopping_session_id == shopping_session_id
    assert owner_event.payload.grocery_item_id == UUID(response.json()["id"])
    assert owner_event.payload.actor_user_id == owner_id
    assert owner_event.payload.item_name == "Milk"
    assert owner_event.payload.sequence_number == 1

    with test_session() as db:
        activity_event = db.query(GroceryActivityEvent).one()
        assert owner_event.event_id == activity_event.id

    Base.metadata.drop_all(engine)
    engine.dispose()
