from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.grocery_item import GroceryItemStatus


class CreateGroceryItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    quantity: Decimal | None = Field(
        default=None,
        gt=0,
        max_digits=10,
        decimal_places=3,
    )
    unit: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=500)
    assigned_to_user_id: UUID | None = None

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        if not normalized:
            raise ValueError("Grocery item name cannot be blank.")
        return normalized

    @field_validator("unit", "notes", mode="before")
    @classmethod
    def normalize_optional_text(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = value.strip()
        return normalized or None

    @field_validator("quantity", mode="before")
    @classmethod
    def reject_boolean_quantity(cls, value: object) -> object:
        if isinstance(value, bool):
            raise ValueError("Quantity must be a number.")
        return value


class GroceryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    shopping_session_id: UUID
    name: str
    quantity: Decimal | None
    unit: str | None
    notes: str | None
    status: GroceryItemStatus
    created_by_user_id: UUID | None
    assigned_to_user_id: UUID | None
    completed_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None
