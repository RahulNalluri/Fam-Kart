from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import Settings, settings
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
