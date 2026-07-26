from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.grocery_activity_event import GroceryActivityType


class GroceryActivityEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    household_id: UUID
    shopping_session_id: UUID
    grocery_item_id: UUID
    actor_user_id: UUID | None
    event_type: GroceryActivityType
    item_name: str
    sequence_number: int
    created_at: datetime
