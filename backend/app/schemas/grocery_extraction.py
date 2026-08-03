from decimal import Decimal
from enum import StrEnum
from typing import Literal
from unicodedata import normalize as unicode_normalize

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CanonicalGroceryKey(StrEnum):
    RICE = "rice"
    MILK = "milk"
    TOMATO = "tomato"
    ONION = "onion"
    POTATO = "potato"
    EGG = "egg"
    CURD = "curd"
    DAL = "dal"
    SALT = "salt"
    SUGAR = "sugar"
    COOKING_OIL = "cooking_oil"
    WHEAT_FLOUR = "wheat_flour"
    CHILLI = "chilli"
    GARLIC = "garlic"
    GINGER = "ginger"


class GroceryUnit(StrEnum):
    KILOGRAM = "kg"
    GRAM = "g"
    LITRE = "l"
    MILLILITRE = "ml"
    PACKET = "packet"
    PIECE = "piece"
    DOZEN = "dozen"
    BOTTLE = "bottle"
    BOX = "box"
    BAG = "bag"
    BUNCH = "bunch"
    CAN = "can"
    JAR = "jar"


def _normalize_required_text(value: object, *, field_name: str) -> object:
    if not isinstance(value, str):
        return value

    normalized = " ".join(unicode_normalize("NFKC", value).split())
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank.")
    return normalized


class GroceryExtractionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=10_000)
    preferred_language: Literal["en", "te"] = "en"

    @field_validator("text", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> object:
        return _normalize_required_text(value, field_name="Grocery command")


class ExtractedGroceryItem(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str = Field(min_length=1, max_length=160)
    canonical_key: CanonicalGroceryKey | None
    quantity: Decimal | None = Field(
        gt=0,
        max_digits=10,
        decimal_places=3,
    )
    unit: GroceryUnit | None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        return _normalize_required_text(value, field_name="Extracted grocery item name")

    @field_validator("quantity", mode="before")
    @classmethod
    def reject_boolean_quantity(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Quantity must be a number.")
        return value

    @model_validator(mode="after")
    def require_quantity_for_unit(self) -> "ExtractedGroceryItem":
        if self.unit is not None and self.quantity is None:
            raise ValueError("A grocery unit requires a quantity.")
        return self


class GroceryExtractionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[ExtractedGroceryItem] = Field(min_length=1, max_length=25)
