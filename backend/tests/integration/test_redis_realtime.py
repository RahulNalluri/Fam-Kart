import asyncio
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings
from app.schemas.realtime import (
    GroceryItemRealtimePayload,
    RealtimeEventEnvelope,
    RealtimeEventType,
)
from app.services.realtime_channels import household_event_channel
from app.services.realtime_connections import RealtimeConnectionManager
from app.services.realtime_publisher import publish_realtime_event
from app.services.realtime_subscription_coordinator import (
    RealtimeSubscriptionCoordinator,
)

pytestmark = pytest.mark.redis_integration

INTEGRATION_CONFIG = Settings(
    environment="testing",
    redis_channel_prefix="familykart-integration",
)


def build_redis_client() -> Redis:
    return Redis.from_url(
        str(INTEGRATION_CONFIG.redis_url),
        decode_responses=True,
    )


def build_event(household_id: UUID) -> RealtimeEventEnvelope:
    return RealtimeEventEnvelope(
        event_id=uuid4(),
        event_type=RealtimeEventType.GROCERY_ITEM_ADDED,
        household_id=household_id,
        occurred_at=datetime.now(UTC),
        payload=GroceryItemRealtimePayload(
            shopping_session_id=uuid4(),
            grocery_item_id=uuid4(),
            actor_user_id=uuid4(),
            item_name="Milk",
            sequence_number=1,
        ),
    )


def build_websocket() -> WebSocket:
    return Mock(spec=WebSocket)


async def wait_for_subscriber_count(
    redis_client: Redis,
    household_id: UUID,
    expected_count: int,
) -> None:
    channel = household_event_channel(household_id, INTEGRATION_CONFIG)
    for _ in range(40):
        subscribers = await redis_client.pubsub_numsub(channel)
        if subscribers and int(subscribers[0][1]) == expected_count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError(
        f"Expected {expected_count} Redis subscribers for household {household_id}.",
    )


async def wait_for_delivery(websocket: WebSocket, expected_count: int = 1) -> None:
    for _ in range(40):
        if websocket.send_text.await_count == expected_count:
            return
        await asyncio.sleep(0.05)
    raise AssertionError("Expected WebSocket delivery did not occur.")


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


def test_event_reaches_two_backend_connection_managers() -> None:
    async def scenario() -> None:
        first_redis = build_redis_client()
        second_redis = build_redis_client()
        first_manager = RealtimeConnectionManager()
        second_manager = RealtimeConnectionManager()
        first_backend = RealtimeSubscriptionCoordinator(
            first_redis,
            first_manager,
            INTEGRATION_CONFIG,
        )
        second_backend = RealtimeSubscriptionCoordinator(
            second_redis,
            second_manager,
            INTEGRATION_CONFIG,
        )
        household_id = uuid4()
        first_websocket = build_websocket()
        second_websocket = build_websocket()
        event = build_event(household_id)

        try:
            await first_manager.register(household_id, uuid4(), first_websocket)
            await second_manager.register(household_id, uuid4(), second_websocket)
            await asyncio.gather(
                first_backend.acquire(household_id),
                second_backend.acquire(household_id),
            )

            subscriber_count = await publish_realtime_event(
                first_redis,
                event,
                INTEGRATION_CONFIG,
            )
            await asyncio.gather(
                wait_for_delivery(first_websocket),
                wait_for_delivery(second_websocket),
            )

            assert subscriber_count == 2
            for websocket in (first_websocket, second_websocket):
                message = websocket.send_text.await_args.args[0]
                assert RealtimeEventEnvelope.model_validate_json(message) == event
        finally:
            await asyncio.gather(first_backend.shutdown(), second_backend.shutdown())
            await first_redis.aclose()
            await second_redis.aclose()

    asyncio.run(scenario())


def test_household_isolation_and_malformed_message_rejection() -> None:
    async def scenario() -> None:
        redis_client = build_redis_client()
        manager = RealtimeConnectionManager()
        backend = RealtimeSubscriptionCoordinator(
            redis_client,
            manager,
            INTEGRATION_CONFIG,
        )
        first_household_id = uuid4()
        second_household_id = uuid4()
        first_websocket = build_websocket()
        second_websocket = build_websocket()

        try:
            await manager.register(first_household_id, uuid4(), first_websocket)
            await manager.register(second_household_id, uuid4(), second_websocket)
            await asyncio.gather(
                backend.acquire(first_household_id),
                backend.acquire(second_household_id),
            )

            first_channel = household_event_channel(
                first_household_id,
                INTEGRATION_CONFIG,
            )
            await redis_client.publish(first_channel, "not-json")
            await asyncio.sleep(0.1)
            first_websocket.send_text.assert_not_awaited()
            second_websocket.send_text.assert_not_awaited()

            event = build_event(first_household_id)
            await publish_realtime_event(redis_client, event, INTEGRATION_CONFIG)
            await wait_for_delivery(first_websocket)

            second_websocket.send_text.assert_not_awaited()
        finally:
            await backend.shutdown()
            await redis_client.aclose()

    asyncio.run(scenario())


def test_reference_counting_uses_one_redis_subscriber() -> None:
    async def scenario() -> None:
        redis_client = build_redis_client()
        backend = RealtimeSubscriptionCoordinator(
            redis_client,
            RealtimeConnectionManager(),
            INTEGRATION_CONFIG,
        )
        household_id = uuid4()

        try:
            await backend.acquire(household_id)
            await backend.acquire(household_id)
            await wait_for_subscriber_count(redis_client, household_id, 1)

            await backend.release(household_id)
            await wait_for_subscriber_count(redis_client, household_id, 1)

            await backend.release(household_id)
            await wait_for_subscriber_count(redis_client, household_id, 0)
        finally:
            await backend.shutdown()
            await redis_client.aclose()

    asyncio.run(scenario())


def test_backend_shutdown_removes_all_redis_subscribers() -> None:
    async def scenario() -> None:
        redis_client = build_redis_client()
        backend = RealtimeSubscriptionCoordinator(
            redis_client,
            RealtimeConnectionManager(),
            INTEGRATION_CONFIG,
        )
        household_ids = (uuid4(), uuid4())

        try:
            await asyncio.gather(
                *(backend.acquire(household_id) for household_id in household_ids),
            )
            for household_id in household_ids:
                await wait_for_subscriber_count(redis_client, household_id, 1)

            await backend.shutdown()

            for household_id in household_ids:
                await wait_for_subscriber_count(redis_client, household_id, 0)
        finally:
            await backend.shutdown()
            await redis_client.aclose()

    asyncio.run(scenario())
