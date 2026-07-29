from uuid import UUID

from app.core.config import Settings, settings


def household_event_channel(
    household_id: UUID,
    config: Settings = settings,
) -> str:
    return (
        f"{config.redis_channel_prefix}:{config.environment}:"
        f"households:{household_id}:events"
    )
