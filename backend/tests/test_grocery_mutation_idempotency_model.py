from app.db.base import Base
from app.models.grocery_mutation_idempotency import GroceryMutationIdempotency


def test_grocery_mutation_idempotency_table_is_registered() -> None:
    assert "grocery_mutation_idempotency" in Base.metadata.tables


def test_grocery_mutation_idempotency_columns_store_request_and_response() -> None:
    columns = GroceryMutationIdempotency.__table__.columns

    assert {
        "mutation_id",
        "user_id",
        "household_id",
        "shopping_session_id",
        "operation",
        "request_hash",
        "response_status",
        "response_body",
        "created_at",
    } == set(columns.keys())
    assert columns["mutation_id"].primary_key is True
    assert columns["request_hash"].type.length == 64
    assert columns["response_body"].nullable is True


def test_grocery_mutation_idempotency_has_cleanup_indexes() -> None:
    index_names = {index.name for index in GroceryMutationIdempotency.__table__.indexes}

    assert "ix_grocery_mutation_idempotency_household_created_at" in index_names
    assert "ix_grocery_mutation_idempotency_user_id" in index_names
    assert "ix_grocery_mutation_idempotency_shopping_session_id" in index_names
