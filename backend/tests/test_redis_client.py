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
    def __init__(self, shutdown_order: list[str] | None = None) -> None:
        self.was_closed = False
        self.shutdown_order = shutdown_order

    async def aclose(self) -> None:
        self.was_closed = True
        if self.shutdown_order is not None:
            self.shutdown_order.append("redis")


class FakeSubscriptionCoordinator:
    latest: "FakeSubscriptionCoordinator | None" = None

    def __init__(self, *args: object) -> None:
        self.was_shutdown = False
        self.shutdown_order = args[-1] if isinstance(args[-1], list) else None
        FakeSubscriptionCoordinator.latest = self

    async def shutdown(self) -> None:
        self.was_shutdown = True
        if self.shutdown_order is not None:
            self.shutdown_order.append("coordinator")


def test_lifespan_stores_and_closes_redis_client(monkeypatch) -> None:
    shutdown_order: list[str] = []
    fake_client = FakeRedisClient(shutdown_order)
    monkeypatch.setattr("app.main.create_redis_client", lambda: fake_client)

    class OrderedFakeCoordinator(FakeSubscriptionCoordinator):
        def __init__(self, *args: object) -> None:
            super().__init__(*args, shutdown_order)

    monkeypatch.setattr(
        "app.main.RealtimeSubscriptionCoordinator",
        OrderedFakeCoordinator,
    )

    async def run_lifespan() -> None:
        async with lifespan(app):
            assert app.state.redis is fake_client
            assert app.state.realtime_subscriptions is not None
            assert not fake_client.was_closed

    asyncio.run(run_lifespan())

    assert fake_client.was_closed
    assert FakeSubscriptionCoordinator.latest is not None
    assert FakeSubscriptionCoordinator.latest.was_shutdown
    assert shutdown_order == ["coordinator", "redis"]
