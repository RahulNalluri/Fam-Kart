from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

import pytest

from app.models import GroceryActivityEvent, GroceryActivityType
from app.schemas.realtime import RealtimeEventEnvelope, RealtimeEventType
from app.services.realtime_events import (
    UnsupportedRealtimeActivityError,
    build_realtime_event,
)

EVENT_TYPE_CASES = [
    (GroceryActivityType.ITEM_ADDED, RealtimeEventType.GROCERY_ITEM_ADDED),
    (GroceryActivityType.ITEM_EDITED, RealtimeEventType.GROCERY_ITEM_EDITED),
    (GroceryActivityType.ITEM_COMPLETED, RealtimeEventType.GROCERY_ITEM_COMPLETED),
    (GroceryActivityType.ITEM_REOPENED, RealtimeEventType.GROCERY_ITEM_REOPENED),
    (GroceryActivityType.ITEM_DELETED, RealtimeEventType.GROCERY_ITEM_DELETED),
]


def build_activity(
    event_type: GroceryActivityType = GroceryActivityType.ITEM_ADDED,
    *,
    actor_user_id=None,
    created_at: datetime | None = None,
) -> GroceryActivityEvent:
    return GroceryActivityEvent(
        id=uuid4(),
        household_id=uuid4(),
        shopping_session_id=uuid4(),
        grocery_item_id=uuid4(),
        actor_user_id=actor_user_id,
        event_type=event_type,
        item_name="Brown rice",
        sequence_number=7,
        created_at=created_at or datetime.now(UTC),
    )


@pytest.mark.parametrize(("activity_type", "realtime_type"), EVENT_TYPE_CASES)
def test_builder_maps_every_grocery_activity_type(
    activity_type: GroceryActivityType,
    realtime_type: RealtimeEventType,
) -> None:
    activity = build_activity(activity_type, actor_user_id=uuid4())

    event = build_realtime_event(activity)

    assert event.event_type == realtime_type


def test_builder_preserves_committed_activity_identity_and_payload() -> None:
    actor_user_id = uuid4()
    occurred_at = datetime.now(UTC).replace(microsecond=0)
    activity = build_activity(
        actor_user_id=actor_user_id,
        created_at=occurred_at,
    )

    event = build_realtime_event(activity)

    assert event.event_id == activity.id
    assert event.household_id == activity.household_id
    assert event.occurred_at == occurred_at
    assert event.payload.shopping_session_id == activity.shopping_session_id
    assert event.payload.grocery_item_id == activity.grocery_item_id
    assert event.payload.actor_user_id == actor_user_id
    assert event.payload.item_name == activity.item_name
    assert event.payload.sequence_number == activity.sequence_number
    assert RealtimeEventEnvelope.model_validate_json(event.model_dump_json()) == event


def test_builder_preserves_missing_actor_for_deleted_user() -> None:
    event = build_realtime_event(
        build_activity(GroceryActivityType.ITEM_DELETED, actor_user_id=None),
    )

    assert event.payload.actor_user_id is None


def test_builder_treats_naive_database_timestamp_as_utc() -> None:
    naive_timestamp = datetime(2026, 7, 30, 9, 15)

    event = build_realtime_event(build_activity(created_at=naive_timestamp))

    assert event.occurred_at == naive_timestamp.replace(tzinfo=UTC)


def test_builder_rejects_unsupported_activity_type() -> None:
    activity = build_activity()
    activity.event_type = cast(GroceryActivityType, "session_completed")

    with pytest.raises(
        UnsupportedRealtimeActivityError,
        match="Unsupported grocery activity type: session_completed",
    ):
        build_realtime_event(activity)
