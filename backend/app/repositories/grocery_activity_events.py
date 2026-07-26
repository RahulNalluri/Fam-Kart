from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.grocery_activity_event import GroceryActivityEvent


class GroceryActivityEventRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def list_for_session(
        self,
        shopping_session_id: UUID,
        *,
        limit: int,
    ) -> list[GroceryActivityEvent]:
        statement = (
            select(GroceryActivityEvent)
            .where(
                GroceryActivityEvent.shopping_session_id == shopping_session_id,
            )
            .order_by(
                GroceryActivityEvent.sequence_number.desc(),
            )
            .limit(limit)
        )
        return list(self.db.execute(statement).scalars().all())
