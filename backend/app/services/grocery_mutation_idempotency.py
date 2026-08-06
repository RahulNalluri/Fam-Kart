import hashlib
import json
from enum import StrEnum
from typing import Any
from uuid import UUID

from app.models.grocery_mutation_idempotency import GroceryMutationIdempotency
from app.repositories.grocery_mutation_idempotency import (
    GroceryMutationIdempotencyContext,
)


class GroceryMutationOperation(StrEnum):
    ADD = "add"
    EDIT = "edit"
    COMPLETE = "complete"
    REOPEN = "reopen"
    DELETE = "delete"


class GroceryMutationIdempotencyConflictError(ValueError):
    pass


def build_grocery_mutation_idempotency_context(
    *,
    mutation_id: UUID,
    user_id: UUID,
    household_id: UUID,
    shopping_session_id: UUID,
    operation: GroceryMutationOperation,
    response_status: int,
    item_id: UUID | None,
    payload: dict[str, Any],
) -> GroceryMutationIdempotencyContext:
    fingerprint_data = {
        "household_id": str(household_id),
        "shopping_session_id": str(shopping_session_id),
        "item_id": str(item_id) if item_id is not None else None,
        "operation": operation.value,
        "payload": payload,
    }
    canonical_request = json.dumps(
        fingerprint_data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    request_hash = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    return GroceryMutationIdempotencyContext(
        mutation_id=mutation_id,
        user_id=user_id,
        household_id=household_id,
        shopping_session_id=shopping_session_id,
        operation=operation.value,
        request_hash=request_hash,
        response_status=response_status,
    )


def validate_grocery_mutation_replay(
    record: GroceryMutationIdempotency,
    context: GroceryMutationIdempotencyContext,
) -> None:
    if (
        record.user_id != context.user_id
        or record.household_id != context.household_id
        or record.shopping_session_id != context.shopping_session_id
        or record.operation != context.operation
        or record.request_hash != context.request_hash
        or record.response_status != context.response_status
    ):
        raise GroceryMutationIdempotencyConflictError
