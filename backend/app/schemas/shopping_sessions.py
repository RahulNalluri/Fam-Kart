from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.shopping_session import ShoppingSessionStatus


class ShoppingSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    household_id: UUID
    created_by_user_id: UUID | None
    status: ShoppingSessionStatus
    created_at: datetime
    completed_at: datetime | None
