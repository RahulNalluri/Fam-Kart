import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from contextlib import suppress
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from redis.asyncio import Redis

from app.core.config import Settings, settings
from app.core.logging import logger
from app.services.realtime_connections import RealtimeConnectionManager
from app.services.realtime_subscriber import (
    RealtimeEventSubscribeError,
    subscribe_to_household_events,
)

RealtimeSubscriber = Callable[
    [Redis, UUID, RealtimeConnectionManager, Settings, asyncio.Event | None],
    Coroutine[Any, Any, None],
]
RecoverySleep = Callable[[float], Awaitable[None]]


class RealtimeSubscriptionStartError(RuntimeError):
    pass


@dataclass
class HouseholdSubscription:
    task: asyncio.Task[None]
    ready_event: asyncio.Event
    reference_count: int


class RealtimeSubscriptionCoordinator:
    def __init__(
        self,
        redis_client: Redis,
        connection_manager: RealtimeConnectionManager,
        config: Settings = settings,
        subscriber: RealtimeSubscriber = subscribe_to_household_events,
        recovery_sleep: RecoverySleep = asyncio.sleep,
    ) -> None:
        self._redis_client = redis_client
        self._connection_manager = connection_manager
        self._config = config
        self._subscriber = subscriber
        self._recovery_sleep = recovery_sleep
        self._subscriptions: dict[UUID, HouseholdSubscription] = {}
        self._lock = asyncio.Lock()

    async def acquire(self, household_id: UUID) -> None:
        async with self._lock:
            subscription = self._subscriptions.get(household_id)
            if subscription is None or subscription.task.done():
                existing_references = (
                    subscription.reference_count if subscription is not None else 0
                )
                subscription = self._start_subscription(
                    household_id,
                    existing_references + 1,
                )
                self._subscriptions[household_id] = subscription
            else:
                subscription.reference_count += 1

        try:
            await self._wait_until_ready(subscription)
        except asyncio.CancelledError:
            await self.release(household_id)
            raise
        except Exception:
            await self.release(household_id)
            raise

    async def release(self, household_id: UUID) -> None:
        task_to_stop: asyncio.Task[None] | None = None
        async with self._lock:
            subscription = self._subscriptions.get(household_id)
            if subscription is None:
                return

            subscription.reference_count -= 1
            if subscription.reference_count <= 0:
                self._subscriptions.pop(household_id)
                task_to_stop = subscription.task

        if task_to_stop is not None:
            task_to_stop.cancel()
            await asyncio.gather(task_to_stop, return_exceptions=True)

    async def subscription_count(self) -> int:
        async with self._lock:
            return len(self._subscriptions)

    async def reference_count(self, household_id: UUID) -> int:
        async with self._lock:
            subscription = self._subscriptions.get(household_id)
            return subscription.reference_count if subscription is not None else 0

    async def shutdown(self) -> None:
        async with self._lock:
            tasks = [subscription.task for subscription in self._subscriptions.values()]
            self._subscriptions.clear()

        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _start_subscription(
        self,
        household_id: UUID,
        reference_count: int,
    ) -> HouseholdSubscription:
        ready_event = asyncio.Event()
        task: asyncio.Task[None] = asyncio.create_task(
            self._maintain_subscription(
                household_id,
                ready_event,
            ),
        )
        task.add_done_callback(self._consume_task_result)
        return HouseholdSubscription(
            task=task,
            ready_event=ready_event,
            reference_count=reference_count,
        )

    async def _maintain_subscription(
        self,
        household_id: UUID,
        ready_event: asyncio.Event,
    ) -> None:
        recovery_attempts = 0
        while True:
            try:
                await self._run_subscription_attempt(
                    household_id,
                    ready_event,
                    recovery_attempts,
                )
            except RealtimeEventSubscribeError as error:
                if not ready_event.is_set():
                    raise

                recovery_attempts += 1
                delay = min(
                    self._config.realtime_reconnect_initial_delay_seconds
                    * (2 ** min(recovery_attempts - 1, 30)),
                    self._config.realtime_reconnect_max_delay_seconds,
                )
                cause = error.__cause__
                logger.warning(
                    "realtime_subscription_recovery_scheduled",
                    household_id=str(household_id),
                    recovery_attempt=recovery_attempts,
                    retry_delay_seconds=delay,
                    error_type=(
                        type(cause).__name__
                        if cause is not None
                        else type(error).__name__
                    ),
                )
                await self._recovery_sleep(delay)

    async def _run_subscription_attempt(
        self,
        household_id: UUID,
        ready_event: asyncio.Event,
        recovery_attempts: int,
    ) -> None:
        attempt_ready = asyncio.Event()
        subscriber_task = asyncio.create_task(
            self._subscriber(
                self._redis_client,
                household_id,
                self._connection_manager,
                self._config,
                attempt_ready,
            ),
        )
        ready_waiter = asyncio.create_task(attempt_ready.wait())
        try:
            done, _ = await asyncio.wait(
                (ready_waiter, subscriber_task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if attempt_ready.is_set():
                if ready_event.is_set():
                    logger.info(
                        "realtime_subscription_recovered",
                        household_id=str(household_id),
                        recovery_attempts=recovery_attempts,
                    )
                else:
                    ready_event.set()

                await subscriber_task
                raise RealtimeEventSubscribeError(
                    "Real-time subscription stopped unexpectedly.",
                )

            if subscriber_task in done:
                await subscriber_task
                raise RealtimeEventSubscribeError(
                    "Real-time subscription stopped before becoming ready.",
                )
        finally:
            ready_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await ready_waiter
            if not subscriber_task.done():
                subscriber_task.cancel()
                await asyncio.gather(subscriber_task, return_exceptions=True)

    async def _wait_until_ready(
        self,
        subscription: HouseholdSubscription,
    ) -> None:
        ready_waiter = asyncio.create_task(subscription.ready_event.wait())
        try:
            done, _ = await asyncio.wait(
                (ready_waiter, subscription.task),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if subscription.task in done:
                try:
                    await subscription.task
                except asyncio.CancelledError as error:
                    raise RealtimeSubscriptionStartError(
                        "Real-time subscription was cancelled during startup.",
                    ) from error
                except Exception as error:
                    raise RealtimeSubscriptionStartError(
                        "Unable to start real-time subscription.",
                    ) from error
                raise RealtimeSubscriptionStartError(
                    "Real-time subscription stopped during startup.",
                )
        finally:
            ready_waiter.cancel()
            with suppress(asyncio.CancelledError):
                await ready_waiter

    @staticmethod
    def _consume_task_result(task: asyncio.Task[None]) -> None:
        if not task.cancelled():
            task.exception()
