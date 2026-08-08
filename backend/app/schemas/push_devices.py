from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.push_device import PushPlatform

EXPO_PUSH_TOKEN_PATTERN = r"^Expo(?:nent)?PushToken\[[A-Za-z0-9_-]+\]$"


class RegisterPushDeviceRequest(BaseModel):
    installation_id: UUID
    expo_push_token: str = Field(
        min_length=20,
        max_length=255,
        pattern=EXPO_PUSH_TOKEN_PATTERN,
    )
    platform: PushPlatform


class PushDeviceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    installation_id: UUID
    platform: PushPlatform
    is_active: bool
    last_registered_at: datetime
    created_at: datetime
    updated_at: datetime
