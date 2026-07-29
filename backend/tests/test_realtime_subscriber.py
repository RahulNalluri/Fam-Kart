import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.schemas.realtime import (
    GroceryItemRealtimePayload,
    RealtimeEventEnvelope,
    RealtimeEventType,
)
from app.services.realtime_connections import RealtimeConnectionManager
from app.services.realtime_subscriber import (
    RealtimeEventSubscribeError,
    subscribe_to_household_events,
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


class FakePubSub:
    def __init__(
        self,
        messages: list[object] | None = None,
        *,
        subscribe_error: Exception | None = None,
        listen_error: Exception | None = None,
        wait_forever: bool = False,
    ) -> None:
        self.messages = messages or []
        self.subscribe_error = subscribe_error
        self.listen_error = listen_error
        self.wait_forever = wait_forever
        self.subscribed_channels: list[str] = []
        self.unsubscribed_channels: list[str] = []
        self.is_closed = False
        self.subscription_started = asyncio.Event()

    async def subscribe(self, channel: str) -> None:
        self.subscribed_channels.append(channel)
        self.subscription_started.set()
        if self.subscribe_error is not None:
            raise self.subscribe_error

    async def listen(self):
        for message in self.messages:
            yield message
        if self.listen_error is not None:
            raise self.listen_error
        if self.wait_forever:
            await asyncio.Event().wait()

    async def unsubscribe(self, channel: str) -> None:
        self.unsubscribed_channels.append(channel)

    async def aclose(self) -> None:
        self.is_closed = True


def build_redis_client(pubsub: FakePubSub) -> Redis:
    redis_client = Mock(spec=Redis)
    redis_client.pubsub.return_value = pubsub
    return redis_client


def build_connection_manager() -> RealtimeConnectionManager:
    manager = Mock(spec=RealtimeConnectionManager)
    manager.broadcast = AsyncMock(return_value=1)
    return manager


def test_valid_event_is_forwarded_from_exact_household_channel() -> None:
    household_id = uuid4()
    event = build_event(household_id)
    pubsub = FakePubSub(
        [
            {"type": "subscribe", "data": 1},
            {"type": "message", "data": event.model_dump_json()},
        ],
    )
    manager = build_connection_manager()
    config = Settings(
        environment="testing",
        redis_channel_prefix="familykart-test",
    )
    ready_event = asyncio.Event()

    asyncio.run(
        subscribe_to_household_events(
            build_redis_client(pubsub),
            household_id,
            manager,
            config,
            ready_event,
        ),
    )

    expected_channel = f"familykart-test:testing:households:{household_id}:events"
    assert pubsub.subscribed_channels == [expected_channel]
    assert pubsub.unsubscribed_channels == [expected_channel]
    assert pubsub.is_closed
    assert ready_event.is_set()
    manager.broadcast.assert_awaited_once_with(household_id, event)


def test_malformed_and_cross_household_messages_are_ignored() -> None:
    household_id = uuid4()
    pubsub = FakePubSub(
        [
            {"type": "message", "data": "not-json"},
            {"type": "message", "data": '{"schema_version": 1}'},
            {
                "type": "message",
                "data": build_event(uuid4()).model_dump_json(),
            },
            {"type": "message", "data": 123},
        ],
    )
    manager = build_connection_manager()

    asyncio.run(
        subscribe_to_household_events(
            build_redis_client(pubsub),
            household_id,
            manager,
        ),
    )

    manager.broadcast.assert_not_awaited()
    assert pubsub.is_closed


@pytest.mark.parametrize("failure_stage", ["subscribe", "listen"])
def test_redis_failures_are_translated_and_resources_are_closed(
    failure_stage: str,
) -> None:
    error = RedisConnectionError("redis unavailable")
    pubsub = FakePubSub(
        subscribe_error=error if failure_stage == "subscribe" else None,
        listen_error=error if failure_stage == "listen" else None,
    )

    with pytest.raises(
        RealtimeEventSubscribeError,
        match="Unable to receive real-time events",
    ) as error_info:
        asyncio.run(
            subscribe_to_household_events(
                build_redis_client(pubsub),
                uuid4(),
                build_connection_manager(),
            ),
        )

    assert error_info.value.__cause__ is error
    assert pubsub.is_closed


def test_cancellation_unsubscribes_and_closes_pubsub() -> None:
    async def scenario() -> FakePubSub:
        pubsub = FakePubSub(wait_forever=True)
        task = asyncio.create_task(
            subscribe_to_household_events(
                build_redis_client(pubsub),
                uuid4(),
                build_connection_manager(),
            ),
        )
        await pubsub.subscription_started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        return pubsub

    pubsub = asyncio.run(scenario())

    assert len(pubsub.unsubscribed_channels) == 1
    assert pubsub.is_closed
