from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from app.models.grocery_activity_event import (
    GroceryActivityEvent,
    GroceryActivityType,
)
from app.models.grocery_item import GroceryItem, GroceryItemStatus


class GroceryItemRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        household_id: UUID,
        shopping_session_id: UUID,
        name: str,
        quantity: Decimal | None,
        unit: str | None,
        notes: str | None,
        created_by_user_id: UUID,
        assigned_to_user_id: UUID | None,
    ) -> GroceryItem:
        item = GroceryItem(
            shopping_session_id=shopping_session_id,
            name=name,
            quantity=quantity,
            unit=unit,
            notes=notes,
            status=GroceryItemStatus.PENDING,
            created_by_user_id=created_by_user_id,
            assigned_to_user_id=assigned_to_user_id,
        )
        self.db.add(item)
        try:
            self.db.flush()
            self._add_activity_event(
                household_id=household_id,
                item=item,
                actor_user_id=created_by_user_id,
                event_type=GroceryActivityType.ITEM_ADDED,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(item)
        return item

    def get_for_session(
        self,
        *,
        item_id: UUID,
        shopping_session_id: UUID,
    ) -> GroceryItem | None:
        statement = select(GroceryItem).where(
            GroceryItem.id == item_id,
            GroceryItem.shopping_session_id == shopping_session_id,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_for_session_for_update(
        self,
        *,
        item_id: UUID,
        shopping_session_id: UUID,
    ) -> GroceryItem | None:
        statement = (
            select(GroceryItem)
            .where(
                GroceryItem.id == item_id,
                GroceryItem.shopping_session_id == shopping_session_id,
            )
            .with_for_update()
        )
        return self.db.execute(statement).scalar_one_or_none()

    def update(
        self,
        item: GroceryItem,
        *,
        household_id: UUID,
        actor_user_id: UUID,
    ) -> GroceryItem:
        try:
            self._add_activity_event(
                household_id=household_id,
                item=item,
                actor_user_id=actor_user_id,
                event_type=GroceryActivityType.ITEM_EDITED,
            )
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(item)
        return item

    def complete(
        self,
        item: GroceryItem,
        *,
        household_id: UUID,
        completed_by_user_id: UUID,
        completed_at: datetime | None = None,
    ) -> GroceryItem:
        effective_completed_at = completed_at or datetime.now(UTC)
        try:
            result = self.db.execute(
                update(GroceryItem)
                .where(
                    GroceryItem.id == item.id,
                    GroceryItem.status == GroceryItemStatus.PENDING,
                )
                .values(
                    status=GroceryItemStatus.COMPLETED,
                    completed_by_user_id=completed_by_user_id,
                    completed_at=effective_completed_at,
                ),
                execution_options={"synchronize_session": False},
            )
        except Exception:
            self.db.rollback()
            raise

        if getattr(result, "rowcount", 0) == 1:
            try:
                self._add_activity_event(
                    household_id=household_id,
                    item=item,
                    actor_user_id=completed_by_user_id,
                    event_type=GroceryActivityType.ITEM_COMPLETED,
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

            self.db.refresh(item)
            return item

        self.db.rollback()
        current = self.db.get(GroceryItem, item.id)
        if current is not None and current.status == GroceryItemStatus.COMPLETED:
            return current
        raise GroceryItemTransitionError

    def reopen(
        self,
        item: GroceryItem,
        *,
        household_id: UUID,
        actor_user_id: UUID,
    ) -> GroceryItem:
        try:
            result = self.db.execute(
                update(GroceryItem)
                .where(
                    GroceryItem.id == item.id,
                    GroceryItem.status == GroceryItemStatus.COMPLETED,
                )
                .values(
                    status=GroceryItemStatus.PENDING,
                    completed_by_user_id=None,
                    completed_at=None,
                ),
                execution_options={"synchronize_session": False},
            )
        except Exception:
            self.db.rollback()
            raise

        if getattr(result, "rowcount", 0) == 1:
            try:
                self._add_activity_event(
                    household_id=household_id,
                    item=item,
                    actor_user_id=actor_user_id,
                    event_type=GroceryActivityType.ITEM_REOPENED,
                )
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

            self.db.refresh(item)
            return item

        self.db.rollback()
        current = self.db.get(GroceryItem, item.id)
        if current is not None and current.status == GroceryItemStatus.PENDING:
            return current
        raise GroceryItemTransitionError

    def delete(
        self,
        item: GroceryItem,
        *,
        household_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        try:
            self._add_activity_event(
                household_id=household_id,
                item=item,
                actor_user_id=actor_user_id,
                event_type=GroceryActivityType.ITEM_DELETED,
            )
            self.db.delete(item)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

    def list_for_session(self, shopping_session_id: UUID) -> list[GroceryItem]:
        statement = (
            select(GroceryItem)
            .where(GroceryItem.shopping_session_id == shopping_session_id)
            .order_by(
                case((GroceryItem.status == GroceryItemStatus.PENDING, 0), else_=1),
                GroceryItem.created_at.asc(),
                GroceryItem.id.asc(),
            )
        )
        return list(self.db.execute(statement).scalars().all())

    def _add_activity_event(
        self,
        *,
        household_id: UUID,
        item: GroceryItem,
        actor_user_id: UUID,
        event_type: GroceryActivityType,
    ) -> None:
        sequence_number = self.db.scalar(
            select(
                func.coalesce(
                    func.max(GroceryActivityEvent.sequence_number),
                    0,
                )
                + 1,
            ).where(
                GroceryActivityEvent.shopping_session_id == item.shopping_session_id,
            ),
        )
        if sequence_number is None:
            raise RuntimeError("Could not allocate grocery activity sequence.")

        self.db.add(
            GroceryActivityEvent(
                household_id=household_id,
                shopping_session_id=item.shopping_session_id,
                grocery_item_id=item.id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                item_name=item.name,
                sequence_number=sequence_number,
            ),
        )


class GroceryItemTransitionError(ValueError):
    pass
