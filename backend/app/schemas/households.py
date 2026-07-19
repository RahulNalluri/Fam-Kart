from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.invitations import normalize_invitation_code
from app.models.household_member import HouseholdRole


class CreateHouseholdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Household name cannot be blank.")
        return normalized


class HouseholdResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    created_at: datetime
    updated_at: datetime


class HouseholdListItem(HouseholdResponse):
    role: HouseholdRole
    joined_at: datetime


class HouseholdMemberResponse(BaseModel):
    user_id: UUID
    display_name: str
    preferred_language: str
    role: HouseholdRole
    joined_at: datetime


class HouseholdInvitationResponse(BaseModel):
    id: UUID
    household_id: UUID
    code: str
    expires_at: datetime


class JoinHouseholdRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invitation_code: str = Field(
        min_length=15,
        max_length=15,
        pattern=r"^FK-[A-HJ-NP-Z2-9]{12}$",
    )

    @field_validator("invitation_code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        if isinstance(value, str):
            return normalize_invitation_code(value)
        return value
