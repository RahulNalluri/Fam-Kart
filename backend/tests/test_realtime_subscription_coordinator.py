import asyncio
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from redis.asyncio import Redis

from app.core.config import Settings
from app.services.realtime_connections import RealtimeConnectionManager
from app.services.realtime_subscriber import RealtimeEventSubscribeError
from app.services.realtime_subscription_coordinator import (
    RealtimeSubscriptionCoordinator,
    RealtimeSubscriptionStartError,
)


def build_redis_client() -> Redis:
    return Mock(spec=Redis)


def build_connection_manager() -> RealtimeConnectionManager:
    return Mock(spec=RealtimeConnectionManager)


class SubscriberHarness:
    def __init__(self) -> None:
        self.started: list[tuple[UUID, RealtimeConnectionManager]] = []
        self.stopped: list[UUID] = []

    async def __call__(
        self,
        redis_client: Redis,
        household_id: UUID,
        connection_manager: RealtimeConnectionManager,
        config: Settings,
        ready_event: asyncio.Event | None,
    ) -> None:
        assert ready_event is not None
        self.started.append((household_id, connection_manager))
        ready_event.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.stopped.append(household_id)


def test_concurrent_connections_share_one_household_subscription() -> None:
    async def scenario() -> SubscriberHarness:
        subscriber = SubscriberHarness()
        household_id = uuid4()
        coordinator = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            build_connection_manager(),
            subscriber=subscriber,
        )

        await asyncio.gather(*(coordinator.acquire(household_id) for _ in range(10)))

        assert len(subscriber.started) == 1
        assert await coordinator.subscription_count() == 1
        assert await coordinator.reference_count(household_id) == 10

        for _ in range(9):
            await coordinator.release(household_id)
        assert await coordinator.subscription_count() == 1

        await coordinator.release(household_id)
        assert await coordinator.subscription_count() == 0
        return subscriber

    subscriber = asyncio.run(scenario())

    assert len(subscriber.stopped) == 1


def test_different_households_use_separate_tasks_until_shutdown() -> None:
    async def scenario() -> SubscriberHarness:
        subscriber = SubscriberHarness()
        first_household_id = uuid4()
        second_household_id = uuid4()
        coordinator = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            build_connection_manager(),
            subscriber=subscriber,
        )

        await coordinator.acquire(first_household_id)
        await coordinator.acquire(second_household_id)

        assert await coordinator.subscription_count() == 2
        await coordinator.shutdown()
        assert await coordinator.subscription_count() == 0
        return subscriber

    subscriber = asyncio.run(scenario())

    assert len(subscriber.started) == 2
    assert sorted(subscriber.stopped) == sorted(
        household_id for household_id, _ in subscriber.started
    )


def test_two_backend_coordinators_subscribe_independently() -> None:
    async def scenario() -> tuple[SubscriberHarness, UUID]:
        subscriber = SubscriberHarness()
        household_id = uuid4()
        first_manager = build_connection_manager()
        second_manager = build_connection_manager()
        first_backend = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            first_manager,
            subscriber=subscriber,
        )
        second_backend = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            second_manager,
            subscriber=subscriber,
        )

        await asyncio.gather(
            first_backend.acquire(household_id),
            second_backend.acquire(household_id),
        )

        assert subscriber.started == [
            (household_id, first_manager),
            (household_id, second_manager),
        ]
        await asyncio.gather(first_backend.shutdown(), second_backend.shutdown())
        return subscriber, household_id

    subscriber, household_id = asyncio.run(scenario())

    assert subscriber.stopped == [household_id, household_id]


def test_initial_subscriber_failure_is_reported_and_reference_is_removed() -> None:
    async def failing_subscriber(
        redis_client: Redis,
        household_id: UUID,
        connection_manager: RealtimeConnectionManager,
        config: Settings,
        ready_event: asyncio.Event | None,
    ) -> None:
        raise RealtimeEventSubscribeError("redis unavailable")

    async def scenario() -> None:
        household_id = uuid4()
        coordinator = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            build_connection_manager(),
            subscriber=failing_subscriber,
        )

        with pytest.raises(
            RealtimeSubscriptionStartError,
            match="Unable to start real-time subscription",
        ) as error_info:
            await coordinator.acquire(household_id)

        assert isinstance(error_info.value.__cause__, RealtimeEventSubscribeError)
        assert await coordinator.subscription_count() == 0
        assert await coordinator.reference_count(household_id) == 0

    asyncio.run(scenario())
