from decimal import Decimal

import pytest

from app.schemas.grocery_extraction import (
    CanonicalGroceryKey,
    GroceryExtractionRequest,
    GroceryExtractionResult,
    GroceryUnit,
)
from app.services.rule_based_grocery_parser import (
    InvalidHouseholdAliasError,
    NoRecognizedGroceryItemsError,
    UnsupportedGroceryCommandError,
    parse_grocery_command,
)


def _parse(
    text: str,
    *,
    aliases: dict[str, str] | None = None,
) -> GroceryExtractionResult:
    return parse_grocery_command(
        GroceryExtractionRequest(text=text, preferred_language="te"),
        household_aliases=aliases,
    )


def test_parser_recognizes_documented_tomato_spelling() -> None:
    result = _parse("Tomatos teskondi")

    assert len(result.items) == 1
    assert result.items[0].name == "Tomatos"
    assert result.items[0].canonical_key is CanonicalGroceryKey.TOMATO
    assert result.items[0].quantity is None


def test_parser_extracts_transliterated_telugu_quantity_and_unit() -> None:
    result = _parse("Palu rendu packets teesukura")

    assert result.items[0].canonical_key is CanonicalGroceryKey.MILK
    assert result.items[0].quantity == Decimal("2")
    assert result.items[0].unit is GroceryUnit.PACKET


def test_parser_extracts_multiple_mixed_language_items() -> None:
    result = _parse("Onions and potatoes add cheyyi")

    assert [item.canonical_key for item in result.items] == [
        CanonicalGroceryKey.ONION,
        CanonicalGroceryKey.POTATO,
    ]
    assert all(item.quantity is None for item in result.items)


def test_parser_extracts_quantity_after_item() -> None:
    result = _parse("Rice 5 kg kavali")

    assert result.items[0].canonical_key is CanonicalGroceryKey.RICE
    assert result.items[0].quantity == Decimal("5")
    assert result.items[0].unit is GroceryUnit.KILOGRAM


def test_parser_extracts_quantity_before_item() -> None:
    result = _parse("Please bring 2 bottles milk")

    assert result.items[0].canonical_key is CanonicalGroceryKey.MILK
    assert result.items[0].quantity == Decimal("2")
    assert result.items[0].unit is GroceryUnit.BOTTLE


def test_parser_supports_native_telugu_command() -> None:
    result = _parse("బియ్యం ఐదు కిలోలు కావాలి")

    assert result.items[0].name == "బియ్యం"
    assert result.items[0].canonical_key is CanonicalGroceryKey.RICE
    assert result.items[0].quantity == Decimal("5")
    assert result.items[0].unit is GroceryUnit.KILOGRAM


def test_parser_normalizes_decimal_and_plural_unit() -> None:
    result = _parse("milk 1.5 litres")

    assert result.items[0].quantity == Decimal("1.5")
    assert result.items[0].unit is GroceryUnit.LITRE


def test_parser_assigns_each_quantity_to_nearest_item() -> None:
    result = _parse("rice 5 kg and milk 2 packets")

    assert [(item.quantity, item.unit) for item in result.items] == [
        (Decimal("5"), GroceryUnit.KILOGRAM),
        (Decimal("2"), GroceryUnit.PACKET),
    ]


def test_parser_assigns_quantity_before_second_item_to_second_item() -> None:
    result = _parse("rice and 2 kg onions")

    assert result.items[0].quantity is None
    assert result.items[1].quantity == Decimal("2")
    assert result.items[1].unit is GroceryUnit.KILOGRAM


def test_parser_prefers_longest_overlapping_grocery_alias() -> None:
    result = _parse("cooking oil 1 litre")

    assert len(result.items) == 1
    assert result.items[0].name == "cooking oil"
    assert result.items[0].canonical_key is CanonicalGroceryKey.COOKING_OIL


def test_parser_supports_authorized_household_alias_data() -> None:
    result = _parse(
        "Maa paalu rendu packets teesukura",
        aliases={"maa paalu": "milk"},
    )

    assert result.items[0].name == "Maa paalu"
    assert result.items[0].canonical_key is CanonicalGroceryKey.MILK
    assert result.items[0].quantity == Decimal("2")


@pytest.mark.parametrize(
    "aliases",
    [
        {"rice": "milk"},
        {"family special": "bread"},
        {"   ": "rice"},
    ],
)
def test_parser_rejects_invalid_household_aliases(aliases: dict[str, str]) -> None:
    with pytest.raises(InvalidHouseholdAliasError):
        _parse("rice", aliases=aliases)


def test_parser_rejects_command_without_known_grocery() -> None:
    with pytest.raises(NoRecognizedGroceryItemsError):
        _parse("Please add bread")


def test_parser_rejects_partial_result_with_unknown_grocery() -> None:
    with pytest.raises(UnsupportedGroceryCommandError):
        _parse("rice and bread")


@pytest.mark.parametrize(
    "text",
    [
        "rice 0 kg",
        "rice 1.0001 kg",
        "rice 12345678.999 kg",
        "rice 2 kg 3 packets",
    ],
)
def test_parser_rejects_invalid_or_ambiguous_quantities(text: str) -> None:
    with pytest.raises(UnsupportedGroceryCommandError):
        _parse(text)


def test_parser_does_not_match_grocery_alias_inside_another_word() -> None:
    with pytest.raises(NoRecognizedGroceryItemsError):
        _parse("Please add gingerbread")


def test_parser_enforces_extraction_item_limit() -> None:
    command = " and ".join(["rice"] * 26)

    with pytest.raises(UnsupportedGroceryCommandError):
        _parse(command)
