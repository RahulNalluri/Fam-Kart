import asyncio
from unittest.mock import AsyncMock, Mock, call, patch
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


class RecoveringSubscriberHarness:
    def __init__(self, *, failures_before_recovery: int) -> None:
        self.failures_before_recovery = failures_before_recovery
        self.attempts = 0
        self.recovered = asyncio.Event()

    async def __call__(
        self,
        redis_client: Redis,
        household_id: UUID,
        connection_manager: RealtimeConnectionManager,
        config: Settings,
        ready_event: asyncio.Event | None,
    ) -> None:
        assert ready_event is not None
        self.attempts += 1
        if self.attempts == 1:
            ready_event.set()
        if self.attempts <= self.failures_before_recovery:
            raise RealtimeEventSubscribeError("redis unavailable")

        ready_event.set()
        self.recovered.set()
        await asyncio.Event().wait()


class RepeatedOutageSubscriberHarness:
    def __init__(self) -> None:
        self.attempts = 0
        self.first_recovery = asyncio.Event()
        self.fail_again = asyncio.Event()
        self.second_recovery = asyncio.Event()

    async def __call__(
        self,
        redis_client: Redis,
        household_id: UUID,
        connection_manager: RealtimeConnectionManager,
        config: Settings,
        ready_event: asyncio.Event | None,
    ) -> None:
        assert ready_event is not None
        self.attempts += 1
        ready_event.set()
        if self.attempts == 1:
            raise RealtimeEventSubscribeError("first outage")
        if self.attempts == 2:
            self.first_recovery.set()
            await self.fail_again.wait()
            raise RealtimeEventSubscribeError("second outage")

        self.second_recovery.set()
        await asyncio.Event().wait()


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


def test_active_subscription_recovers_with_bounded_exponential_backoff() -> None:
    async def scenario(
        logger: Mock,
    ) -> tuple[
        RecoveringSubscriberHarness,
        AsyncMock,
        RealtimeConnectionManager,
        UUID,
    ]:
        subscriber = RecoveringSubscriberHarness(failures_before_recovery=3)
        recovery_sleep = AsyncMock()
        household_id = uuid4()
        connection_manager = build_connection_manager()
        config = Settings(
            realtime_reconnect_initial_delay_seconds=0.5,
            realtime_reconnect_max_delay_seconds=0.75,
        )
        coordinator = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            connection_manager,
            config,
            subscriber,
            recovery_sleep,
        )

        await coordinator.acquire(household_id)
        await subscriber.recovered.wait()
        for _ in range(10):
            if logger.info.called:
                break
            await asyncio.sleep(0)

        assert await coordinator.subscription_count() == 1
        assert await coordinator.reference_count(household_id) == 1
        await coordinator.shutdown()
        return subscriber, recovery_sleep, connection_manager, household_id

    with patch("app.services.realtime_subscription_coordinator.logger") as logger:
        subscriber, recovery_sleep, connection_manager, household_id = asyncio.run(
            scenario(logger),
        )

    assert subscriber.attempts == 4
    assert recovery_sleep.await_args_list == [call(0.5), call(0.75), call(0.75)]
    assert logger.warning.call_count == 3
    assert connection_manager.disconnect_household.await_count == 3
    connection_manager.disconnect_household.assert_awaited_with(
        household_id,
        code=1013,
        reason="Real-time service unavailable.",
    )
    logger.info.assert_called_once_with(
        "realtime_subscription_recovered",
        household_id=str(household_id),
        recovery_attempts=3,
    )


def test_final_disconnect_cancels_pending_subscription_recovery() -> None:
    async def scenario() -> tuple[RecoveringSubscriberHarness, int]:
        subscriber = RecoveringSubscriberHarness(failures_before_recovery=1)
        sleep_started = asyncio.Event()

        async def blocking_recovery_sleep(delay: float) -> None:
            sleep_started.set()
            await asyncio.Event().wait()

        household_id = uuid4()
        coordinator = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            build_connection_manager(),
            subscriber=subscriber,
            recovery_sleep=blocking_recovery_sleep,
        )

        await coordinator.acquire(household_id)
        await sleep_started.wait()
        await coordinator.release(household_id)

        return subscriber, await coordinator.subscription_count()

    subscriber, subscription_count = asyncio.run(scenario())

    assert subscriber.attempts == 1
    assert subscription_count == 0


def test_recovery_backoff_resets_after_each_successful_subscription() -> None:
    async def scenario() -> tuple[AsyncMock, RepeatedOutageSubscriberHarness]:
        recovery_sleep = AsyncMock()
        subscriber = RepeatedOutageSubscriberHarness()
        household_id = uuid4()
        coordinator = RealtimeSubscriptionCoordinator(
            build_redis_client(),
            build_connection_manager(),
            Settings(
                realtime_reconnect_initial_delay_seconds=0.5,
                realtime_reconnect_max_delay_seconds=2,
            ),
            subscriber,
            recovery_sleep,
        )

        await coordinator.acquire(household_id)
        await subscriber.first_recovery.wait()
        subscriber.fail_again.set()
        await subscriber.second_recovery.wait()
        await coordinator.shutdown()
        return recovery_sleep, subscriber

    recovery_sleep, subscriber = asyncio.run(scenario())

    assert subscriber.attempts == 3
    assert recovery_sleep.await_args_list == [call(0.5), call(0.5)]
