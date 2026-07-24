from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    GroceryItem,
    GroceryItemStatus,
    Household,
    ShoppingSession,
    User,
)
from app.repositories.grocery_items import GroceryItemRepository


def create_test_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_dependencies(
    db: Session,
    *,
    suffix: str,
) -> tuple[User, ShoppingSession]:
    user = User(
        email=f"grocery-repository-{suffix}@example.com",
        display_name="Grocery Repository User",
        password_hash="!",
        preferred_language="en",
    )
    household = Household(name=f"Grocery Repository {suffix}")
    db.add_all([user, household])
    db.flush()
    shopping_session = ShoppingSession(
        household_id=household.id,
        created_by_user_id=user.id,
    )
    db.add(shopping_session)
    db.commit()
    return user, shopping_session


def test_repository_creates_pending_item_with_all_input_fields() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="create")
        repository = GroceryItemRepository(db)

        item = repository.create(
            shopping_session_id=shopping_session.id,
            name="Tomatoes - టమాటాలు",
            quantity=Decimal("2.500"),
            unit="kg",
            notes="Ripe only",
            created_by_user_id=user.id,
            assigned_to_user_id=user.id,
        )

        assert item.shopping_session_id == shopping_session.id
        assert item.name == "Tomatoes - టమాటాలు"
        assert item.quantity == Decimal("2.500")
        assert item.unit == "kg"
        assert item.notes == "Ripe only"
        assert item.status == GroceryItemStatus.PENDING
        assert item.created_by_user_id == user.id
        assert item.assigned_to_user_id == user.id
        assert item.completed_by_user_id is None
        assert item.completed_at is None
    finally:
        db.close()


def test_repository_creates_name_only_item() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="name-only")
        repository = GroceryItemRepository(db)

        item = repository.create(
            shopping_session_id=shopping_session.id,
            name="Milk",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )

        assert item.name == "Milk"
        assert item.quantity is None
        assert item.unit is None
        assert item.notes is None
        assert item.assigned_to_user_id is None
    finally:
        db.close()


def test_repository_scopes_item_lookup_to_shopping_session() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="scope")
        _, other_session = create_dependencies(db, suffix="other-scope")
        repository = GroceryItemRepository(db)
        item = repository.create(
            shopping_session_id=shopping_session.id,
            name="Rice",
            quantity=Decimal("5"),
            unit="kg",
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )

        assert (
            repository.get_for_session(
                item_id=item.id,
                shopping_session_id=shopping_session.id,
            )
            is not None
        )
        assert (
            repository.get_for_session(
                item_id=item.id,
                shopping_session_id=other_session.id,
            )
            is None
        )
    finally:
        db.close()


def test_repository_lists_only_session_items_pending_first() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="list")
        _, other_session = create_dependencies(db, suffix="hidden-list")
        now = datetime.now(UTC)
        pending_older = GroceryItem(
            shopping_session_id=shopping_session.id,
            name="Rice",
            status=GroceryItemStatus.PENDING,
            created_by_user_id=user.id,
            created_at=now - timedelta(minutes=2),
        )
        pending_newer = GroceryItem(
            shopping_session_id=shopping_session.id,
            name="Milk",
            status=GroceryItemStatus.PENDING,
            created_by_user_id=user.id,
            created_at=now - timedelta(minutes=1),
        )
        completed = GroceryItem(
            shopping_session_id=shopping_session.id,
            name="Onions",
            status=GroceryItemStatus.COMPLETED,
            created_by_user_id=user.id,
            created_at=now - timedelta(minutes=3),
            completed_at=now,
        )
        hidden = GroceryItem(
            shopping_session_id=other_session.id,
            name="Hidden",
            status=GroceryItemStatus.PENDING,
            created_by_user_id=user.id,
            created_at=now - timedelta(days=1),
        )
        db.add_all([completed, pending_newer, pending_older, hidden])
        db.commit()
        repository = GroceryItemRepository(db)

        items = repository.list_for_session(shopping_session.id)

        assert [item.id for item in items] == [
            pending_older.id,
            pending_newer.id,
            completed.id,
        ]
    finally:
        db.close()


def test_repository_rolls_back_when_creation_commit_fails() -> None:
    db = Mock(spec=Session)
    db.commit.side_effect = RuntimeError("database unavailable")
    repository = GroceryItemRepository(db)

    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.create(
            shopping_session_id=uuid4(),
            name="Rice",
            quantity=Decimal("5"),
            unit="kg",
            notes=None,
            created_by_user_id=uuid4(),
            assigned_to_user_id=None,
        )

    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()
