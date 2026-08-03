from types import MappingProxyType
from typing import Final
from unicodedata import normalize as unicode_normalize

STANDARD_GROCERY_TERMS_BY_KEY: Final[dict[str, tuple[str, ...]]] = {
    "rice": ("rice", "బియ్యం", "biyyam"),
    "milk": ("milk", "పాలు", "palu"),
    "tomato": (
        "tomato",
        "tomatoes",
        "tomatos",
        "టమాటా",
        "టమాటాలు",
        "tamata",
        "tamatalu",
    ),
    "onion": (
        "onion",
        "onions",
        "ఉల్లిపాయ",
        "ఉల్లిపాయలు",
        "ullipaya",
        "ullipayalu",
    ),
    "potato": (
        "potato",
        "potatoes",
        "బంగాళాదుంప",
        "బంగాళాదుంపలు",
        "bangaladumpa",
        "bangaladumpalu",
        "aloo",
    ),
    "egg": ("egg", "eggs", "గుడ్డు", "గుడ్లు", "guddu", "gudlu"),
    "curd": ("curd", "yogurt", "yoghurt", "పెరుగు", "perugu"),
    "dal": ("dal", "lentil", "lentils", "పప్పు", "pappu"),
    "salt": ("salt", "ఉప్పు", "uppu"),
    "sugar": ("sugar", "చక్కెర", "chakkera"),
    "cooking_oil": (
        "cooking_oil",
        "oil",
        "cooking oil",
        "నూనె",
        "వంట నూనె",
        "nune",
        "noone",
        "vanta nune",
    ),
    "wheat_flour": (
        "wheat_flour",
        "wheat flour",
        "atta",
        "గోధుమ పిండి",
        "godhuma pindi",
    ),
    "chilli": (
        "chilli",
        "chillies",
        "chili",
        "chilies",
        "మిరపకాయ",
        "మిరపకాయలు",
        "mirapakaya",
        "mirapakayalu",
    ),
    "garlic": ("garlic", "వెల్లుల్లి", "vellulli"),
    "ginger": ("ginger", "అల్లం", "allam"),
}

CANONICAL_GROCERY_KEYS: Final[frozenset[str]] = frozenset(
    STANDARD_GROCERY_TERMS_BY_KEY,
)


def clean_grocery_alias(value: str) -> str:
    return " ".join(unicode_normalize("NFKC", value).split())


def normalize_grocery_alias(value: str) -> str:
    return clean_grocery_alias(value).casefold()


def normalize_canonical_grocery_key(value: str) -> str:
    return unicode_normalize("NFKC", value).strip().casefold()


def _build_standard_alias_owners() -> MappingProxyType[str, str]:
    owners: dict[str, str] = {}
    for canonical_key, terms in STANDARD_GROCERY_TERMS_BY_KEY.items():
        for term in (canonical_key, *terms):
            normalized_term = normalize_grocery_alias(term)
            existing_key = owners.get(normalized_term)
            if existing_key is not None and existing_key != canonical_key:
                raise RuntimeError(
                    f'Grocery term "{normalized_term}" belongs to both '
                    f'"{existing_key}" and "{canonical_key}".',
                )
            owners[normalized_term] = canonical_key
    return MappingProxyType(owners)


STANDARD_GROCERY_ALIAS_OWNERS: Final[MappingProxyType[str, str]] = (
    _build_standard_alias_owners()
)


def is_canonical_grocery_key(value: str) -> bool:
    return normalize_canonical_grocery_key(value) in CANONICAL_GROCERY_KEYS


def standard_grocery_alias_owner(value: str) -> str | None:
    return STANDARD_GROCERY_ALIAS_OWNERS.get(normalize_grocery_alias(value))
