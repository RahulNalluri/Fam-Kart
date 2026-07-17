from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UpdateUserProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    preferred_language: Literal["en", "te"] | None = None

    @field_validator("display_name")
    @classmethod
    def normalize_display_name(cls, value: str | None) -> str | None:
        if value is None:
            return None

        normalized = value.strip()
        if not normalized:
            raise ValueError("Display name cannot be blank.")
        return normalized

    @model_validator(mode="after")
    def require_update(self) -> "UpdateUserProfileRequest":
        if self.display_name is None and self.preferred_language is None:
            raise ValueError("At least one profile field must be provided.")
        return self
