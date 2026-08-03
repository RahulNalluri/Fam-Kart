from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.core.grocery_dictionary import CANONICAL_GROCERY_KEYS
from app.schemas.grocery_extraction import (
    CanonicalGroceryKey,
    ExtractedGroceryItem,
    GroceryExtractionRequest,
    GroceryExtractionResult,
    GroceryUnit,
)


def test_extraction_request_normalizes_mixed_language_command() -> None:
    request = GroceryExtractionRequest(
        text="  Onions   and  potatoes add cheyyi  ",
        preferred_language="te",
    )

    assert request.text == "Onions and potatoes add cheyyi"
    assert request.preferred_language == "te"


def test_extraction_request_preserves_telugu_text() -> None:
    request = GroceryExtractionRequest(text="పాలు రెండు ప్యాకెట్లు తీసుకురా")

    assert request.text == "పాలు రెండు ప్యాకెట్లు తీసుకురా"
    assert request.preferred_language == "en"


@pytest.mark.parametrize(
    "payload",
    [
        {"text": ""},
        {"text": "   "},
        {"text": "Rice", "preferred_language": "hi"},
        {"text": "Rice", "household_id": "not-accepted"},
        {"text": "x" * 10_001},
    ],
)
def test_extraction_request_rejects_invalid_input(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        GroceryExtractionRequest.model_validate(payload)


def test_extracted_item_supports_quantity_and_canonical_unit() -> None:
    item = ExtractedGroceryItem(
        name="  Rice  ",
        canonical_key="rice",
        quantity="5.000",
        unit="kg",
    )

    assert item.name == "Rice"
    assert item.canonical_key is CanonicalGroceryKey.RICE
    assert item.quantity == Decimal("5.000")
    assert item.unit is GroceryUnit.KILOGRAM


def test_extracted_item_supports_unknown_name_without_quantity() -> None:
    item = ExtractedGroceryItem(
        name="Dragon fruit",
        canonical_key=None,
        quantity=None,
        unit=None,
    )

    assert item.name == "Dragon fruit"
    assert item.canonical_key is None
    assert item.quantity is None
    assert item.unit is None


def test_extraction_result_supports_multiple_items() -> None:
    result = GroceryExtractionResult(
        items=[
            {
                "name": "Milk",
                "canonical_key": "milk",
                "quantity": 2,
                "unit": "packet",
            },
            {
                "name": "Onions",
                "canonical_key": "onion",
                "quantity": None,
                "unit": None,
            },
        ],
    )

    assert len(result.items) == 2
    assert result.items[0].quantity == Decimal("2")
    assert result.items[0].unit is GroceryUnit.PACKET
    assert result.items[1].canonical_key is CanonicalGroceryKey.ONION


@pytest.mark.parametrize(
    "payload",
    [
        {
            "name": "Rice",
            "canonical_key": "bread",
            "quantity": None,
            "unit": None,
        },
        {
            "name": "Rice",
            "canonical_key": "rice",
            "quantity": 0,
            "unit": "kg",
        },
        {
            "name": "Rice",
            "canonical_key": "rice",
            "quantity": True,
            "unit": "kg",
        },
        {
            "name": "Rice",
            "canonical_key": "rice",
            "quantity": "1.0001",
            "unit": "kg",
        },
        {
            "name": "Rice",
            "canonical_key": "rice",
            "quantity": "12345678.999",
            "unit": "kg",
        },
        {
            "name": "Rice",
            "canonical_key": "rice",
            "quantity": 1,
            "unit": "kilogram",
        },
        {
            "name": "Rice",
            "canonical_key": "rice",
            "quantity": None,
            "unit": "kg",
        },
        {
            "name": "Rice",
            "canonical_key": "rice",
            "quantity": None,
            "unit": None,
            "confidence": 0.9,
        },
    ],
)
def test_extracted_item_rejects_invalid_structured_output(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ExtractedGroceryItem.model_validate(payload)


def test_extracted_item_requires_all_nullable_fields() -> None:
    with pytest.raises(ValidationError):
        ExtractedGroceryItem(name="Milk")


@pytest.mark.parametrize("size", [0, 26])
def test_extraction_result_enforces_item_count_limit(size: int) -> None:
    item = {
        "name": "Milk",
        "canonical_key": "milk",
        "quantity": None,
        "unit": None,
    }

    with pytest.raises(ValidationError):
        GroceryExtractionResult(items=[item] * size)


def test_canonical_schema_keys_match_grocery_dictionary() -> None:
    assert {key.value for key in CanonicalGroceryKey} == CANONICAL_GROCERY_KEYS


def test_result_json_schema_rejects_extra_fields_and_enumerates_values() -> None:
    schema = GroceryExtractionResult.model_json_schema()

    assert schema["additionalProperties"] is False
    assert schema["$defs"]["ExtractedGroceryItem"]["additionalProperties"] is False
    assert schema["$defs"]["CanonicalGroceryKey"]["enum"] == [
        key.value for key in CanonicalGroceryKey
    ]
    assert schema["$defs"]["GroceryUnit"]["enum"] == [
        unit.value for unit in GroceryUnit
    ]
