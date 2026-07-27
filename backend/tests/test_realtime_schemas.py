import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.schemas.realtime import (
    GroceryItemRealtimePayload,
    RealtimeEventEnvelope,
    RealtimeEventType,
)


def build_event_data() -> dict[str, object]:
    return {
        "schema_version": 1,
        "event_id": uuid4(),
        "event_type": RealtimeEventType.GROCERY_ITEM_ADDED,
        "household_id": uuid4(),
        "occurred_at": datetime.now(UTC),
        "payload": {
            "shopping_session_id": uuid4(),
            "grocery_item_id": uuid4(),
            "actor_user_id": uuid4(),
            "item_name": "  Brown   rice  ",
            "sequence_number": 1,
        },
    }


def test_realtime_event_normalizes_and_serializes_contract() -> None:
    event = RealtimeEventEnvelope.model_validate(build_event_data())

    assert event.schema_version == 1
    assert event.event_type == RealtimeEventType.GROCERY_ITEM_ADDED
    assert event.payload.item_name == "Brown rice"
    assert event.occurred_at.tzinfo is not None

    encoded = event.model_dump_json()
    decoded = json.loads(encoded)
    assert decoded["schema_version"] == 1
    assert decoded["event_type"] == "grocery.item_added"
    assert decoded["payload"]["item_name"] == "Brown rice"
    assert RealtimeEventEnvelope.model_validate_json(encoded) == event


@pytest.mark.parametrize("event_type", list(RealtimeEventType))
def test_contract_accepts_every_grocery_event_type(
    event_type: RealtimeEventType,
) -> None:
    data = build_event_data()
    data["event_type"] = event_type

    event = RealtimeEventEnvelope.model_validate(data)

    assert event.event_type == event_type


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("schema_version", 2),
        ("event_type", "grocery.unknown"),
        ("occurred_at", datetime.now()),
        ("unexpected", "value"),
    ],
)
def test_contract_rejects_invalid_envelope_fields(
    field: str,
    value: object,
) -> None:
    data = build_event_data()
    data[field] = value

    with pytest.raises(ValidationError):
        RealtimeEventEnvelope.model_validate(data)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("item_name", "   "),
        ("sequence_number", 0),
        ("password_hash", "must-not-be-accepted"),
    ],
)
def test_contract_rejects_invalid_or_sensitive_payload_fields(
    field: str,
    value: object,
) -> None:
    data = build_event_data()
    payload = data["payload"]
    assert isinstance(payload, dict)
    payload[field] = value

    with pytest.raises(ValidationError):
        RealtimeEventEnvelope.model_validate(data)


def test_contract_allows_deleted_actor_account() -> None:
    data = build_event_data()
    payload = data["payload"]
    assert isinstance(payload, dict)
    payload["actor_user_id"] = None

    event = RealtimeEventEnvelope.model_validate(data)

    assert event.payload.actor_user_id is None


def test_contract_models_are_immutable() -> None:
    event = RealtimeEventEnvelope.model_validate(build_event_data())

    with pytest.raises(ValidationError):
        event.payload = GroceryItemRealtimePayload(
            shopping_session_id=uuid4(),
            grocery_item_id=uuid4(),
            actor_user_id=None,
            item_name="Milk",
            sequence_number=2,
        )
