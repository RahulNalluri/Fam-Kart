import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from redis.asyncio import Redis
from redis.exceptions import ConnectionError as RedisConnectionError

from app.core.config import Settings
from app.schemas.realtime import (
    GroceryItemRealtimePayload,
    RealtimeEventEnvelope,
    RealtimeEventType,
)
from app.services.realtime_publisher import (
    RealtimeEventPublishError,
    publish_realtime_event,
    try_publish_realtime_event,
)


def build_event() -> RealtimeEventEnvelope:
    return RealtimeEventEnvelope(
        event_id=uuid4(),
        event_type=RealtimeEventType.GROCERY_ITEM_ADDED,
        household_id=uuid4(),
        occurred_at=datetime.now(UTC),
        payload=GroceryItemRealtimePayload(
            shopping_session_id=uuid4(),
            grocery_item_id=uuid4(),
            actor_user_id=uuid4(),
            item_name="Milk",
            sequence_number=1,
        ),
    )


def build_redis_client(*, subscriber_count: int = 0) -> Redis:
    redis_client = Mock(spec=Redis)
    redis_client.publish = AsyncMock(return_value=subscriber_count)
    return redis_client


def test_publisher_uses_household_channel_and_complete_event_json() -> None:
    redis_client = build_redis_client(subscriber_count=2)
    event = build_event()
    config = Settings(
        environment="testing",
        redis_channel_prefix="familykart-test",
    )

    subscriber_count = asyncio.run(
        publish_realtime_event(redis_client, event, config),
    )

    assert subscriber_count == 2
    redis_client.publish.assert_awaited_once()
    channel, message = redis_client.publish.await_args.args
    assert channel == (
        f"familykart-test:testing:households:{event.household_id}:events"
    )
    assert json.loads(message) == json.loads(event.model_dump_json())


def test_publisher_returns_zero_when_no_subscribers_are_active() -> None:
    redis_client = build_redis_client()

    subscriber_count = asyncio.run(
        publish_realtime_event(redis_client, build_event()),
    )

    assert subscriber_count == 0


def test_publisher_translates_redis_failures() -> None:
    redis_client = build_redis_client()
    redis_client.publish.side_effect = RedisConnectionError("connection failed")

    with pytest.raises(
        RealtimeEventPublishError,
        match="Unable to publish real-time event",
    ) as error_info:
        asyncio.run(publish_realtime_event(redis_client, build_event()))

    assert isinstance(error_info.value.__cause__, RedisConnectionError)


def test_best_effort_publisher_reports_success() -> None:
    redis_client = build_redis_client(subscriber_count=1)

    published = asyncio.run(
        try_publish_realtime_event(redis_client, build_event()),
    )

    assert published is True


def test_best_effort_publisher_treats_zero_subscribers_as_success() -> None:
    redis_client = build_redis_client(subscriber_count=0)

    published = asyncio.run(
        try_publish_realtime_event(redis_client, build_event()),
    )

    assert published is True


def test_best_effort_publisher_swallows_redis_failure() -> None:
    redis_client = build_redis_client()
    redis_client.publish.side_effect = RedisConnectionError("connection failed")
    event = build_event()

    with patch("app.services.realtime_publisher.logger") as logger:
        published = asyncio.run(
            try_publish_realtime_event(redis_client, event),
        )

    assert published is False
    logger.warning.assert_called_once_with(
        "realtime_event_publish_failed",
        event_id=str(event.event_id),
        household_id=str(event.household_id),
        event_type=event.event_type.value,
        failure_policy="best_effort",
        error_type="ConnectionError",
    )
