import asyncio
import json
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest
from fastapi import WebSocket

from app.schemas.realtime import (
    GroceryItemRealtimePayload,
    RealtimeEventEnvelope,
    RealtimeEventType,
)
from app.services.realtime_connections import RealtimeConnectionManager


def build_event(household_id: UUID) -> RealtimeEventEnvelope:
    return RealtimeEventEnvelope(
        event_id=uuid4(),
        event_type=RealtimeEventType.GROCERY_ITEM_ADDED,
        household_id=household_id,
        occurred_at=datetime.now(UTC),
        payload=GroceryItemRealtimePayload(
            shopping_session_id=uuid4(),
            grocery_item_id=uuid4(),
            actor_user_id=uuid4(),
            item_name="Rice",
            sequence_number=1,
        ),
    )


def build_websocket() -> WebSocket:
    return Mock(spec=WebSocket)


def test_registration_supports_multiple_users_devices_and_households() -> None:
    async def scenario() -> None:
        manager = RealtimeConnectionManager()
        household_id = uuid4()
        other_household_id = uuid4()
        user_id = uuid4()
        other_user_id = uuid4()
        first_device = build_websocket()
        second_device = build_websocket()
        other_household_device = build_websocket()

        await manager.register(household_id, user_id, first_device)
        await manager.register(household_id, user_id, first_device)
        await manager.register(household_id, user_id, second_device)
        await manager.register(
            other_household_id,
            other_user_id,
            other_household_device,
        )

        assert await manager.connection_count() == 3
        assert await manager.connection_count(household_id) == 2
        assert await manager.connection_count(household_id, user_id) == 2
        assert await manager.connection_count(household_id, other_user_id) == 0

    asyncio.run(scenario())


def test_unregister_removes_empty_user_and_household_buckets() -> None:
    async def scenario() -> None:
        manager = RealtimeConnectionManager()
        household_id = uuid4()
        user_id = uuid4()
        websocket = build_websocket()

        await manager.register(household_id, user_id, websocket)
        await manager.unregister(household_id, user_id, websocket)
        await manager.unregister(household_id, user_id, websocket)

        assert await manager.connection_count() == 0
        assert await manager.connection_count(household_id) == 0

    asyncio.run(scenario())


def test_broadcast_delivers_validated_json_only_to_target_household() -> None:
    async def scenario() -> None:
        manager = RealtimeConnectionManager()
        household_id = uuid4()
        other_household_id = uuid4()
        first_connection = build_websocket()
        second_connection = build_websocket()
        isolated_connection = build_websocket()
        user_id = uuid4()
        await manager.register(household_id, user_id, first_connection)
        await manager.register(household_id, user_id, second_connection)
        await manager.register(other_household_id, uuid4(), isolated_connection)
        event = build_event(household_id)

        delivered = await manager.broadcast(household_id, event)

        assert delivered == 2
        for connection in (first_connection, second_connection):
            connection.send_text.assert_awaited_once()
            encoded = connection.send_text.await_args.args[0]
            assert json.loads(encoded)["event_id"] == str(event.event_id)
        isolated_connection.send_text.assert_not_awaited()

    asyncio.run(scenario())


def test_broadcast_removes_failed_connection_without_blocking_healthy_one() -> None:
    async def scenario() -> None:
        manager = RealtimeConnectionManager()
        household_id = uuid4()
        healthy_connection = build_websocket()
        failed_connection = build_websocket()
        failed_connection.send_text.side_effect = RuntimeError("connection closed")
        await manager.register(household_id, uuid4(), healthy_connection)
        await manager.register(household_id, uuid4(), failed_connection)

        delivered = await manager.broadcast(
            household_id,
            build_event(household_id),
        )

        assert delivered == 1
        healthy_connection.send_text.assert_awaited_once()
        failed_connection.send_text.assert_awaited_once()
        assert await manager.connection_count(household_id) == 1

    asyncio.run(scenario())


def test_broadcast_rejects_event_for_different_household() -> None:
    async def scenario() -> None:
        manager = RealtimeConnectionManager()
        household_id = uuid4()
        connection = build_websocket()
        await manager.register(household_id, uuid4(), connection)

        with pytest.raises(ValueError, match="does not belong"):
            await manager.broadcast(household_id, build_event(uuid4()))

        connection.send_text.assert_not_awaited()

    asyncio.run(scenario())
