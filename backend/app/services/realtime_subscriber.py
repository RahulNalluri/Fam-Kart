import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress
from typing import Protocol, cast
from uuid import UUID

from pydantic import ValidationError
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, settings
from app.schemas.realtime import RealtimeEventEnvelope
from app.services.realtime_channels import household_event_channel
from app.services.realtime_connections import RealtimeConnectionManager


class RealtimeEventSubscribeError(RuntimeError):
    pass


class RealtimePubSub(Protocol):
    async def subscribe(self, channel: str) -> None: ...

    def listen(self) -> AsyncIterator[object]: ...

    async def unsubscribe(self, channel: str) -> None: ...

    async def aclose(self) -> None: ...


async def subscribe_to_household_events(
    redis_client: Redis,
    household_id: UUID,
    connection_manager: RealtimeConnectionManager,
    config: Settings = settings,
    ready_event: asyncio.Event | None = None,
) -> None:
    channel = household_event_channel(household_id, config)
    pubsub = cast(RealtimePubSub, redis_client.pubsub())

    try:
        await pubsub.subscribe(channel)
        if ready_event is not None:
            ready_event.set()
        async for message in pubsub.listen():
            event = _validate_household_message(message, household_id)
            if event is not None:
                await connection_manager.broadcast(household_id, event)
    except RedisError as error:
        raise RealtimeEventSubscribeError(
            "Unable to receive real-time events.",
        ) from error
    finally:
        with suppress(RedisError):
            await pubsub.unsubscribe(channel)
        with suppress(RedisError):
            await pubsub.aclose()


def _validate_household_message(
    message: object,
    household_id: UUID,
) -> RealtimeEventEnvelope | None:
    if not isinstance(message, dict) or message.get("type") != "message":
        return None

    data = message.get("data")
    if not isinstance(data, (str, bytes, bytearray)):
        return None

    try:
        event = RealtimeEventEnvelope.model_validate_json(data)
    except ValidationError:
        return None

    if event.household_id != household_id:
        return None
    return event
