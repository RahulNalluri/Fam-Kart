from typing import cast

from fastapi import Request
from redis.asyncio import Redis

from app.core.config import Settings, settings


def create_redis_client(config: Settings = settings) -> Redis:
    return Redis.from_url(
        str(config.redis_url),
        decode_responses=True,
    )


def get_redis(request: Request) -> Redis:
    return cast(Redis, request.app.state.redis)
