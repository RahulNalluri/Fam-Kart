from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.grocery_item import GroceryItem
from app.models.grocery_mutation_idempotency import GroceryMutationIdempotency

IDEMPOTENCY_PRIMARY_KEY = "pk_grocery_mutation_idempotency"


class DuplicateGroceryMutationIdempotencyError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class GroceryMutationIdempotencyContext:
    mutation_id: UUID
    user_id: UUID
    household_id: UUID
    shopping_session_id: UUID
    operation: str
    request_hash: str
    response_status: int


class GroceryMutationIdempotencyRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get(self, mutation_id: UUID) -> GroceryMutationIdempotency | None:
        return self.db.get(GroceryMutationIdempotency, mutation_id)

    def begin(
        self,
        context: GroceryMutationIdempotencyContext,
    ) -> GroceryMutationIdempotency:
        record = GroceryMutationIdempotency(
            mutation_id=context.mutation_id,
            user_id=context.user_id,
            household_id=context.household_id,
            shopping_session_id=context.shopping_session_id,
            operation=context.operation,
            request_hash=context.request_hash,
            response_status=context.response_status,
            response_body=None,
        )
        self.db.add(record)
        try:
            self.db.flush()
        except IntegrityError as error:
            self.db.rollback()
            if _is_idempotency_conflict(error):
                raise DuplicateGroceryMutationIdempotencyError from error
            raise
        return record

    def complete_with_item(
        self,
        record: GroceryMutationIdempotency,
        item: GroceryItem,
    ) -> None:
        record.response_body = _serialize_grocery_item(item)

    def complete_without_body(self, record: GroceryMutationIdempotency) -> None:
        record.response_body = None


def _serialize_grocery_item(item: GroceryItem) -> dict[str, object]:
    quantity = item.quantity
    return {
        "id": str(item.id),
        "shopping_session_id": str(item.shopping_session_id),
        "name": item.name,
        "quantity": str(quantity) if isinstance(quantity, Decimal) else quantity,
        "unit": item.unit,
        "notes": item.notes,
        "status": item.status.value,
        "created_by_user_id": (
            str(item.created_by_user_id)
            if item.created_by_user_id is not None
            else None
        ),
        "assigned_to_user_id": (
            str(item.assigned_to_user_id)
            if item.assigned_to_user_id is not None
            else None
        ),
        "completed_by_user_id": (
            str(item.completed_by_user_id)
            if item.completed_by_user_id is not None
            else None
        ),
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
        "completed_at": (
            item.completed_at.isoformat() if item.completed_at is not None else None
        ),
    }


def _is_idempotency_conflict(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    error_text = str(error.orig).lower()
    return (
        constraint_name == IDEMPOTENCY_PRIMARY_KEY
        or IDEMPOTENCY_PRIMARY_KEY in error_text
        or (
            "unique constraint failed" in error_text
            and "grocery_mutation_idempotency.mutation_id" in error_text
        )
    )
