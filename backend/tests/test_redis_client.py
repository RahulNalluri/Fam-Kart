import asyncio

from app.core.config import Settings
from app.core.redis import create_redis_client
from app.main import app, lifespan


def test_create_redis_client_uses_configured_url() -> None:
    config = Settings(redis_url="redis://localhost:6380/3")

    client = create_redis_client(config)

    try:
        connection_kwargs = client.connection_pool.connection_kwargs
        assert connection_kwargs["host"] == "localhost"
        assert connection_kwargs["port"] == 6380
        assert connection_kwargs["db"] == 3
        assert connection_kwargs["decode_responses"] is True
    finally:
        asyncio.run(client.aclose())


class FakeRedisClient:
    def __init__(self) -> None:
        self.was_closed = False

    async def aclose(self) -> None:
        self.was_closed = True


def test_lifespan_stores_and_closes_redis_client(monkeypatch) -> None:
    fake_client = FakeRedisClient()
    monkeypatch.setattr("app.main.create_redis_client", lambda: fake_client)

    async def run_lifespan() -> None:
        async with lifespan(app):
            assert app.state.redis is fake_client
            assert not fake_client.was_closed

    asyncio.run(run_lifespan())

    assert fake_client.was_closed
