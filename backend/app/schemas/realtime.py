from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator


class RealtimeEventType(StrEnum):
    GROCERY_ITEM_ADDED = "grocery.item_added"
    GROCERY_ITEM_EDITED = "grocery.item_edited"
    GROCERY_ITEM_COMPLETED = "grocery.item_completed"
    GROCERY_ITEM_REOPENED = "grocery.item_reopened"
    GROCERY_ITEM_DELETED = "grocery.item_deleted"


class GroceryItemRealtimePayload(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    shopping_session_id: UUID
    grocery_item_id: UUID
    actor_user_id: UUID | None
    item_name: str = Field(min_length=1, max_length=160)
    sequence_number: int = Field(gt=0)

    @field_validator("item_name", mode="before")
    @classmethod
    def normalize_item_name(cls, value: object) -> object:
        if not isinstance(value, str):
            return value

        normalized = " ".join(value.split())
        if not normalized:
            raise ValueError("Grocery item name cannot be blank.")
        return normalized


class RealtimeEventEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    event_id: UUID
    event_type: RealtimeEventType
    household_id: UUID
    occurred_at: AwareDatetime
    payload: GroceryItemRealtimePayload
