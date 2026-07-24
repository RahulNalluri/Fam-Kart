from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models import GroceryItem, GroceryItemStatus
from app.schemas.grocery_items import CreateGroceryItemRequest, GroceryItemResponse


def test_create_request_normalizes_multilingual_item_fields() -> None:
    assigned_to_user_id = uuid4()

    request = CreateGroceryItemRequest(
        name="  Tomatoes - టమాటాలు  ",
        quantity="2.500",
        unit="  kg  ",
        notes="  Ripe only  ",
        assigned_to_user_id=assigned_to_user_id,
    )

    assert request.name == "Tomatoes - టమాటాలు"
    assert request.quantity == Decimal("2.500")
    assert request.unit == "kg"
    assert request.notes == "Ripe only"
    assert request.assigned_to_user_id == assigned_to_user_id


def test_create_request_supports_name_only() -> None:
    request = CreateGroceryItemRequest(name="Milk")

    assert request.name == "Milk"
    assert request.quantity is None
    assert request.unit is None
    assert request.notes is None
    assert request.assigned_to_user_id is None


def test_create_request_converts_blank_optional_text_to_none() -> None:
    request = CreateGroceryItemRequest(
        name="Rice",
        unit="   ",
        notes="\n\t",
    )

    assert request.unit is None
    assert request.notes is None


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 161},
        {"name": "Rice", "quantity": 0},
        {"name": "Rice", "quantity": -1},
        {"name": "Rice", "quantity": True},
        {"name": "Rice", "quantity": "12345678.999"},
        {"name": "Rice", "quantity": "1.0001"},
        {"name": "Rice", "unit": "x" * 33},
        {"name": "Rice", "notes": "x" * 501},
        {"name": "Rice", "status": "completed"},
    ],
)
def test_create_request_rejects_invalid_or_server_managed_fields(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        CreateGroceryItemRequest.model_validate(payload)


def test_response_validates_from_grocery_item_model() -> None:
    now = datetime.now(UTC)
    item = GroceryItem(
        id=uuid4(),
        shopping_session_id=uuid4(),
        name="Rice",
        quantity=Decimal("5.000"),
        unit="kg",
        notes="Sona Masoori",
        status=GroceryItemStatus.PENDING,
        created_by_user_id=uuid4(),
        assigned_to_user_id=None,
        completed_by_user_id=None,
        created_at=now,
        updated_at=now,
        completed_at=None,
    )

    response = GroceryItemResponse.model_validate(item)

    assert response.id == item.id
    assert response.shopping_session_id == item.shopping_session_id
    assert response.quantity == Decimal("5.000")
    assert response.status == GroceryItemStatus.PENDING
    assert response.completed_at is None
    assert set(response.model_dump()) == {
        "id",
        "shopping_session_id",
        "name",
        "quantity",
        "unit",
        "notes",
        "status",
        "created_by_user_id",
        "assigned_to_user_id",
        "completed_by_user_id",
        "created_at",
        "updated_at",
        "completed_at",
    }
