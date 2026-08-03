import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Final
from unicodedata import category as unicode_category

from pydantic import ValidationError

from app.core.grocery_dictionary import (
    CANONICAL_GROCERY_KEYS,
    STANDARD_GROCERY_ALIAS_OWNERS,
    clean_grocery_alias,
    normalize_canonical_grocery_key,
    normalize_grocery_alias,
    standard_grocery_alias_owner,
)
from app.schemas.grocery_extraction import (
    CanonicalGroceryKey,
    ExtractedGroceryItem,
    GroceryExtractionRequest,
    GroceryExtractionResult,
    GroceryUnit,
)


class RuleBasedParserError(ValueError):
    pass


class NoRecognizedGroceryItemsError(RuleBasedParserError):
    pass


class UnsupportedGroceryCommandError(RuleBasedParserError):
    pass


class InvalidHouseholdAliasError(RuleBasedParserError):
    pass


@dataclass(frozen=True, slots=True)
class _ItemMatch:
    start: int
    end: int
    canonical_key: str
    display_name: str


@dataclass(frozen=True, slots=True)
class _QuantityMatch:
    start: int
    end: int
    quantity: Decimal
    unit: GroceryUnit | None


NUMBER_VALUES: Final[Mapping[str, Decimal]] = MappingProxyType(
    {
        "one": Decimal("1"),
        "two": Decimal("2"),
        "three": Decimal("3"),
        "four": Decimal("4"),
        "five": Decimal("5"),
        "six": Decimal("6"),
        "seven": Decimal("7"),
        "eight": Decimal("8"),
        "nine": Decimal("9"),
        "ten": Decimal("10"),
        "half": Decimal("0.5"),
        "okati": Decimal("1"),
        "rendu": Decimal("2"),
        "moodu": Decimal("3"),
        "nalugu": Decimal("4"),
        "aidu": Decimal("5"),
        "aaru": Decimal("6"),
        "edu": Decimal("7"),
        "enimidi": Decimal("8"),
        "tommidi": Decimal("9"),
        "padi": Decimal("10"),
        "ఒకటి": Decimal("1"),
        "రెండు": Decimal("2"),
        "మూడు": Decimal("3"),
        "నాలుగు": Decimal("4"),
        "ఐదు": Decimal("5"),
        "ఆరు": Decimal("6"),
        "ఏడు": Decimal("7"),
        "ఎనిమిది": Decimal("8"),
        "తొమ్మిది": Decimal("9"),
        "పది": Decimal("10"),
    },
)

UNIT_ALIASES: Final[Mapping[GroceryUnit, tuple[str, ...]]] = MappingProxyType(
    {
        GroceryUnit.KILOGRAM: (
            "kg",
            "kgs",
            "kilogram",
            "kilograms",
            "kilo",
            "kilos",
            "కిలో",
            "కిలోలు",
        ),
        GroceryUnit.GRAM: ("g", "gm", "gms", "gram", "grams", "గ్రాము", "గ్రాములు"),
        GroceryUnit.LITRE: (
            "l",
            "ltr",
            "ltrs",
            "litre",
            "litres",
            "liter",
            "liters",
            "లీటరు",
            "లీటర్లు",
        ),
        GroceryUnit.MILLILITRE: (
            "ml",
            "millilitre",
            "millilitres",
            "milliliter",
            "milliliters",
        ),
        GroceryUnit.PACKET: (
            "packet",
            "packets",
            "pack",
            "packs",
            "packetlu",
            "ప్యాకెట్",
            "ప్యాకెట్లు",
        ),
        GroceryUnit.PIECE: ("piece", "pieces", "pc", "pcs", "ముక్క", "ముక్కలు"),
        GroceryUnit.DOZEN: ("dozen", "dozens", "డజను", "డజన్లు"),
        GroceryUnit.BOTTLE: ("bottle", "bottles", "సీసా", "సీసాలు"),
        GroceryUnit.BOX: ("box", "boxes", "డబ్బా", "డబ్బాలు"),
        GroceryUnit.BAG: ("bag", "bags", "సంచి", "సంచులు"),
        GroceryUnit.BUNCH: ("bunch", "bunches", "కట్ట", "కట్టలు"),
        GroceryUnit.CAN: ("can", "cans"),
        GroceryUnit.JAR: ("jar", "jars"),
    },
)

ALLOWED_COMMAND_WORDS: Final[frozenset[str]] = frozenset(
    {
        "a",
        "add",
        "an",
        "and",
        "bring",
        "buy",
        "chey",
        "cheyyandi",
        "cheyyi",
        "for",
        "get",
        "kavali",
        "konandi",
        "list",
        "me",
        "need",
        "of",
        "please",
        "plus",
        "some",
        "techandi",
        "teesukondi",
        "teesukura",
        "teskondi",
        "teskura",
        "the",
        "thechandi",
        "tisukondi",
        "tisukura",
        "to",
        "want",
        "wanted",
        "ఇంకా",
        "కావాలి",
        "కొనండి",
        "జోడించండి",
        "జోడించు",
        "తీసుకోండి",
        "తీసుకురా",
        "తెచ్చండి",
        "మరియు",
    },
)


def _build_unit_owners() -> Mapping[str, GroceryUnit]:
    owners: dict[str, GroceryUnit] = {}
    for unit, aliases in UNIT_ALIASES.items():
        for alias in aliases:
            normalized_alias = normalize_grocery_alias(alias)
            existing_unit = owners.get(normalized_alias)
            if existing_unit is not None and existing_unit is not unit:
                raise RuntimeError(f'Unit alias "{alias}" has multiple owners.')
            owners[normalized_alias] = unit
    return MappingProxyType(owners)


UNIT_OWNERS: Final[Mapping[str, GroceryUnit]] = _build_unit_owners()


def _phrase_pattern(phrases: Mapping[str, object] | frozenset[str]) -> str:
    return "|".join(
        re.escape(phrase)
        for phrase in sorted(phrases, key=lambda value: (-len(value), value))
    )


NUMBER_PATTERN: Final[str] = rf"(?:\d+(?:\.\d+)?|{_phrase_pattern(NUMBER_VALUES)})"
UNIT_PATTERN: Final[str] = _phrase_pattern(UNIT_OWNERS)
QUANTITY_PATTERN: Final[re.Pattern[str]] = re.compile(
    rf"(?<!\w)(?P<number>{NUMBER_PATTERN})(?!\w)"
    rf"(?:\s+(?P<unit>{UNIT_PATTERN})(?!\w))?",
)


def _build_alias_owners(
    household_aliases: Mapping[str, str] | None,
) -> dict[str, str]:
    owners = dict(STANDARD_GROCERY_ALIAS_OWNERS)
    if household_aliases is None:
        return owners

    for alias, canonical_key in household_aliases.items():
        normalized_alias = normalize_grocery_alias(alias)
        normalized_key = normalize_canonical_grocery_key(canonical_key)
        if not normalized_alias or normalized_key not in CANONICAL_GROCERY_KEYS:
            raise InvalidHouseholdAliasError(
                "Household aliases require a non-blank alias and canonical key.",
            )
        standard_owner = standard_grocery_alias_owner(normalized_alias)
        if standard_owner is not None and standard_owner != normalized_key:
            raise InvalidHouseholdAliasError(
                "A household alias cannot remap a standard grocery term.",
            )
        owners[normalized_alias] = normalized_key
    return owners


def _find_items(
    cleaned_text: str,
    normalized_text: str,
    alias_owners: Mapping[str, str],
) -> list[_ItemMatch]:
    candidates: list[_ItemMatch] = []
    for alias, canonical_key in alias_owners.items():
        pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)")
        for match in pattern.finditer(normalized_text):
            candidates.append(
                _ItemMatch(
                    start=match.start(),
                    end=match.end(),
                    canonical_key=canonical_key,
                    display_name=cleaned_text[match.start() : match.end()],
                ),
            )

    selected: list[_ItemMatch] = []
    for candidate in sorted(
        candidates,
        key=lambda item: (-(item.end - item.start), item.start),
    ):
        if any(
            candidate.start < existing.end and existing.start < candidate.end
            for existing in selected
        ):
            continue
        selected.append(candidate)
    return sorted(selected, key=lambda item: item.start)


def _find_quantities(normalized_text: str) -> list[_QuantityMatch]:
    quantities: list[_QuantityMatch] = []
    for match in QUANTITY_PATTERN.finditer(normalized_text):
        number_text = match.group("number")
        try:
            quantity = (
                NUMBER_VALUES[number_text]
                if number_text in NUMBER_VALUES
                else Decimal(number_text)
            )
        except InvalidOperation as error:
            raise UnsupportedGroceryCommandError(
                "The grocery quantity could not be understood.",
            ) from error

        unit_text = match.group("unit")
        quantities.append(
            _QuantityMatch(
                start=match.start(),
                end=match.end(),
                quantity=quantity,
                unit=UNIT_OWNERS.get(unit_text) if unit_text is not None else None,
            ),
        )
    return quantities


def _distance(quantity: _QuantityMatch, item: _ItemMatch) -> int:
    if quantity.end <= item.start:
        return item.start - quantity.end
    if quantity.start >= item.end:
        return quantity.start - item.end
    return 0


def _assign_quantities(
    items: list[_ItemMatch],
    quantities: list[_QuantityMatch],
) -> dict[int, _QuantityMatch]:
    assignments: dict[int, _QuantityMatch] = {}
    for quantity in quantities:
        item_index = min(
            range(len(items)),
            key=lambda index: (_distance(quantity, items[index]), index),
        )
        existing = assignments.get(item_index)
        if existing is not None:
            raise UnsupportedGroceryCommandError(
                "More than one quantity was found for the same grocery item.",
            )
        assignments[item_index] = quantity
    return assignments


def _command_words(value: str) -> list[str]:
    cleaned_characters = [
        character if unicode_category(character)[0] in {"L", "M", "N"} else " "
        for character in value
    ]
    return "".join(cleaned_characters).split()


def _validate_residual_text(
    normalized_text: str,
    items: list[_ItemMatch],
    quantities: list[_QuantityMatch],
) -> None:
    characters = list(normalized_text)
    matched_spans = [
        *((item.start, item.end) for item in items),
        *((quantity.start, quantity.end) for quantity in quantities),
    ]
    for start, end in matched_spans:
        characters[start:end] = " " * (end - start)

    unsupported_words = [
        word
        for word in _command_words("".join(characters))
        if word not in ALLOWED_COMMAND_WORDS
    ]
    if unsupported_words:
        raise UnsupportedGroceryCommandError(
            "The command contains grocery words the rule-based parser "
            "cannot understand.",
        )


def parse_grocery_command(
    request: GroceryExtractionRequest,
    *,
    household_aliases: Mapping[str, str] | None = None,
) -> GroceryExtractionResult:
    cleaned_text = clean_grocery_alias(request.text)
    normalized_text = cleaned_text.casefold()
    item_matches = _find_items(
        cleaned_text,
        normalized_text,
        _build_alias_owners(household_aliases),
    )
    if not item_matches:
        raise NoRecognizedGroceryItemsError(
            "No supported grocery items were found in the command.",
        )
    if len(item_matches) > 25:
        raise UnsupportedGroceryCommandError(
            "A grocery command cannot contain more than 25 items.",
        )

    quantity_matches = _find_quantities(normalized_text)
    _validate_residual_text(normalized_text, item_matches, quantity_matches)
    assignments = _assign_quantities(item_matches, quantity_matches)

    try:
        extracted_items = [
            ExtractedGroceryItem(
                name=item.display_name,
                canonical_key=CanonicalGroceryKey(item.canonical_key),
                quantity=(
                    assignments[index].quantity if index in assignments else None
                ),
                unit=assignments[index].unit if index in assignments else None,
            )
            for index, item in enumerate(item_matches)
        ]
        return GroceryExtractionResult(items=extracted_items)
    except ValidationError as error:
        raise UnsupportedGroceryCommandError(
            "The parsed grocery command contains an invalid quantity or unit.",
        ) from error
