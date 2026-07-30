from datetime import UTC, datetime
from types import MappingProxyType

from app.models.grocery_activity_event import (
    GroceryActivityEvent,
    GroceryActivityType,
)
from app.schemas.realtime import (
    GroceryItemRealtimePayload,
    RealtimeEventEnvelope,
    RealtimeEventType,
)

ACTIVITY_EVENT_TYPE_MAP = MappingProxyType(
    {
        GroceryActivityType.ITEM_ADDED: RealtimeEventType.GROCERY_ITEM_ADDED,
        GroceryActivityType.ITEM_EDITED: RealtimeEventType.GROCERY_ITEM_EDITED,
        GroceryActivityType.ITEM_COMPLETED: RealtimeEventType.GROCERY_ITEM_COMPLETED,
        GroceryActivityType.ITEM_REOPENED: RealtimeEventType.GROCERY_ITEM_REOPENED,
        GroceryActivityType.ITEM_DELETED: RealtimeEventType.GROCERY_ITEM_DELETED,
    },
)


class UnsupportedRealtimeActivityError(ValueError):
    pass


def build_realtime_event(
    activity: GroceryActivityEvent,
) -> RealtimeEventEnvelope:
    try:
        event_type = ACTIVITY_EVENT_TYPE_MAP[activity.event_type]
    except KeyError as error:
        raise UnsupportedRealtimeActivityError(
            f"Unsupported grocery activity type: {activity.event_type!s}",
        ) from error

    return RealtimeEventEnvelope(
        event_id=activity.id,
        event_type=event_type,
        household_id=activity.household_id,
        occurred_at=_as_aware_datetime(activity.created_at),
        payload=GroceryItemRealtimePayload(
            shopping_session_id=activity.shopping_session_id,
            grocery_item_id=activity.grocery_item_id,
            actor_user_id=activity.actor_user_id,
            item_name=activity.item_name,
            sequence_number=activity.sequence_number,
        ),
    )


def _as_aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
