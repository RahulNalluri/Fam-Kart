from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.grocery_dictionary import (
    clean_grocery_alias,
    normalize_canonical_grocery_key,
)


class CreateHouseholdGroceryAliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1, max_length=160)
    canonical_key: str = Field(min_length=1, max_length=64)

    @field_validator("alias")
    @classmethod
    def normalize_alias_display(cls, value: str) -> str:
        normalized = clean_grocery_alias(value)
        if not normalized:
            raise ValueError("Alias cannot be blank.")
        return normalized

    @field_validator("canonical_key")
    @classmethod
    def normalize_canonical_key(cls, value: str) -> str:
        normalized = normalize_canonical_grocery_key(value)
        if not normalized:
            raise ValueError("Canonical key cannot be blank.")
        return normalized


class UpdateHouseholdGroceryAliasRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    alias: str | None = Field(default=None, min_length=1, max_length=160)
    canonical_key: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("alias")
    @classmethod
    def normalize_alias_display(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = clean_grocery_alias(value)
        if not normalized:
            raise ValueError("Alias cannot be blank.")
        return normalized

    @field_validator("canonical_key")
    @classmethod
    def normalize_canonical_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = normalize_canonical_grocery_key(value)
        if not normalized:
            raise ValueError("Canonical key cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def require_update(self) -> "UpdateHouseholdGroceryAliasRequest":
        if self.alias is None and self.canonical_key is None:
            raise ValueError("At least one alias field must be provided.")
        return self


class HouseholdGroceryAliasResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    household_id: UUID
    alias: str
    canonical_key: str
    created_by_user_id: UUID | None
    created_at: datetime
    updated_at: datetime
