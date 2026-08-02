from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.grocery_dictionary import (
    CANONICAL_GROCERY_KEYS,
    normalize_grocery_alias,
    standard_grocery_alias_owner,
)
from app.schemas.household_grocery_aliases import (
    CreateHouseholdGroceryAliasRequest,
    HouseholdGroceryAliasResponse,
    UpdateHouseholdGroceryAliasRequest,
)


def test_backend_dictionary_defines_current_canonical_items() -> None:
    assert CANONICAL_GROCERY_KEYS == {
        "rice",
        "milk",
        "tomato",
        "onion",
        "potato",
        "egg",
        "curd",
        "dal",
        "salt",
        "sugar",
        "cooking_oil",
        "wheat_flour",
        "chilli",
        "garlic",
        "ginger",
    }


@pytest.mark.parametrize(
    ("term", "owner"),
    [
        (" TOMATOES ", "tomato"),
        ("టమాటాలు", "tomato"),
        ("Palu", "milk"),
        ("godhuma   pindi", "wheat_flour"),
    ],
)
def test_backend_dictionary_resolves_protected_standard_terms(
    term: str,
    owner: str,
) -> None:
    assert standard_grocery_alias_owner(term) == owner


def test_alias_normalization_handles_unicode_case_and_whitespace() -> None:
    assert normalize_grocery_alias("  ＭＩＬＫ   ") == "milk"


def test_create_schema_normalizes_display_and_canonical_key() -> None:
    request = CreateHouseholdGroceryAliasRequest(
        alias="  Morning   Milk  ",
        canonical_key=" MILK ",
    )

    assert request.alias == "Morning Milk"
    assert request.canonical_key == "milk"


@pytest.mark.parametrize(
    "payload",
    [
        {"alias": "  ", "canonical_key": "milk"},
        {"alias": "family milk", "canonical_key": "  "},
        {"alias": "family milk", "canonical_key": "milk", "extra": True},
    ],
)
def test_create_schema_rejects_invalid_payload(payload: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        CreateHouseholdGroceryAliasRequest.model_validate(payload)


def test_update_schema_requires_a_field_and_normalizes_values() -> None:
    with pytest.raises(ValidationError):
        UpdateHouseholdGroceryAliasRequest()

    request = UpdateHouseholdGroceryAliasRequest(
        alias="  Curry   Onions ",
        canonical_key=" ONION ",
    )
    assert request.alias == "Curry Onions"
    assert request.canonical_key == "onion"

    with pytest.raises(ValidationError):
        UpdateHouseholdGroceryAliasRequest(canonical_key="  ")


def test_alias_response_serializes_database_contract() -> None:
    now = datetime.now(UTC)
    response = HouseholdGroceryAliasResponse(
        id=uuid4(),
        household_id=uuid4(),
        alias="Morning milk",
        canonical_key="milk",
        created_by_user_id=uuid4(),
        created_at=now,
        updated_at=now,
    )

    assert response.alias == "Morning milk"
    assert response.canonical_key == "milk"
