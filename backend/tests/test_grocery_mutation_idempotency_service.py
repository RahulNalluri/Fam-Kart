from uuid import uuid4

import pytest

from app.models.grocery_mutation_idempotency import GroceryMutationIdempotency
from app.services.grocery_mutation_idempotency import (
    GroceryMutationIdempotencyConflictError,
    GroceryMutationOperation,
    build_grocery_mutation_idempotency_context,
    validate_grocery_mutation_replay,
)


def test_request_fingerprint_is_stable_across_payload_key_order() -> None:
    mutation_id = uuid4()
    user_id = uuid4()
    household_id = uuid4()
    session_id = uuid4()
    item_id = uuid4()
    first = build_grocery_mutation_idempotency_context(
        mutation_id=mutation_id,
        user_id=user_id,
        household_id=household_id,
        shopping_session_id=session_id,
        operation=GroceryMutationOperation.EDIT,
        response_status=200,
        item_id=item_id,
        payload={"name": "Rice", "quantity": "5.000"},
    )
    second = build_grocery_mutation_idempotency_context(
        mutation_id=mutation_id,
        user_id=user_id,
        household_id=household_id,
        shopping_session_id=session_id,
        operation=GroceryMutationOperation.EDIT,
        response_status=200,
        item_id=item_id,
        payload={"quantity": "5.000", "name": "Rice"},
    )

    assert first.request_hash == second.request_hash
    assert len(first.request_hash) == 64


def test_replay_validation_rejects_a_changed_request() -> None:
    context = build_grocery_mutation_idempotency_context(
        mutation_id=uuid4(),
        user_id=uuid4(),
        household_id=uuid4(),
        shopping_session_id=uuid4(),
        operation=GroceryMutationOperation.ADD,
        response_status=201,
        item_id=None,
        payload={"name": "Rice"},
    )
    record = GroceryMutationIdempotency(
        mutation_id=context.mutation_id,
        user_id=context.user_id,
        household_id=context.household_id,
        shopping_session_id=context.shopping_session_id,
        operation=context.operation,
        request_hash="0" * 64,
        response_status=context.response_status,
    )

    with pytest.raises(GroceryMutationIdempotencyConflictError):
        validate_grocery_mutation_replay(record, context)
