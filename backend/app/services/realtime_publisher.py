from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, settings
from app.core.logging import logger
from app.schemas.realtime import RealtimeEventEnvelope
from app.services.realtime_channels import household_event_channel


class RealtimeEventPublishError(RuntimeError):
    pass


async def publish_realtime_event(
    redis_client: Redis,
    event: RealtimeEventEnvelope,
    config: Settings = settings,
) -> int:
    channel = household_event_channel(event.household_id, config)
    message = event.model_dump_json()

    try:
        return await redis_client.publish(channel, message)
    except RedisError as error:
        raise RealtimeEventPublishError("Unable to publish real-time event.") from error


async def try_publish_realtime_event(
    redis_client: Redis,
    event: RealtimeEventEnvelope,
    config: Settings = settings,
) -> bool:
    try:
        await publish_realtime_event(redis_client, event, config)
    except RealtimeEventPublishError as error:
        cause = error.__cause__
        logger.warning(
            "realtime_event_publish_failed",
            event_id=str(event.event_id),
            household_id=str(event.household_id),
            event_type=event.event_type.value,
            failure_policy="best_effort",
            error_type=(
                type(cause).__name__ if cause is not None else type(error).__name__
            ),
        )
        return False
    return True
