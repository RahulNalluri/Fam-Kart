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
from app.repositories.grocery_items import (
    DuplicatePendingGroceryItemError,
    GroceryItemRepository,
)


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
            household_id=shopping_session.household_id,
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
            household_id=shopping_session.household_id,
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


def test_repository_rejects_case_insensitive_pending_duplicate() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="duplicate")
        repository = GroceryItemRepository(db)
        create_arguments = {
            "household_id": shopping_session.household_id,
            "shopping_session_id": shopping_session.id,
            "quantity": None,
            "unit": None,
            "notes": None,
            "created_by_user_id": user.id,
            "assigned_to_user_id": None,
        }
        repository.create(name="Milk", **create_arguments)

        with pytest.raises(DuplicatePendingGroceryItemError):
            repository.create(name="  mIlK  ", **create_arguments)

        assert len(repository.list_for_session(shopping_session.id)) == 1
    finally:
        db.close()


def test_repository_allows_completed_name_and_name_in_another_session() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="allowed-duplicate")
        other_user, other_session = create_dependencies(
            db,
            suffix="other-allowed-duplicate",
        )
        repository = GroceryItemRepository(db)
        first = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Rice",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        repository.complete(
            first,
            household_id=shopping_session.household_id,
            completed_by_user_id=user.id,
        )

        same_session_item = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="rice",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        other_session_item = repository.create(
            household_id=other_session.household_id,
            shopping_session_id=other_session.id,
            name="RICE",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=other_user.id,
            assigned_to_user_id=None,
        )

        assert same_session_item.status == GroceryItemStatus.PENDING
        assert other_session_item.status == GroceryItemStatus.PENDING
    finally:
        db.close()


def test_repository_scopes_item_lookup_to_shopping_session() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="scope")
        _, other_session = create_dependencies(db, suffix="other-scope")
        repository = GroceryItemRepository(db)
        item = repository.create(
            household_id=shopping_session.household_id,
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
    db.execute.return_value.first.return_value = None
    db.commit.side_effect = RuntimeError("database unavailable")
    repository = GroceryItemRepository(db)

    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.create(
            household_id=uuid4(),
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


def test_repository_updates_and_persists_item_fields() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="update")
        repository = GroceryItemRepository(db)
        item = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Rice",
            quantity=Decimal("5"),
            unit="kg",
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )

        locked_item = repository.get_for_session_for_update(
            item_id=item.id,
            shopping_session_id=shopping_session.id,
        )
        assert locked_item is not None
        locked_item.name = "Brown rice"
        locked_item.quantity = Decimal("2.500")
        locked_item.assigned_to_user_id = user.id

        updated = repository.update(
            locked_item,
            household_id=shopping_session.household_id,
            actor_user_id=user.id,
        )

        assert updated.name == "Brown rice"
        assert updated.quantity == Decimal("2.500")
        assert updated.assigned_to_user_id == user.id
    finally:
        db.close()


def test_repository_update_lookup_remains_scoped_to_session() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="update-scope")
        _, other_session = create_dependencies(db, suffix="other-update-scope")
        repository = GroceryItemRepository(db)
        item = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Rice",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )

        assert (
            repository.get_for_session_for_update(
                item_id=item.id,
                shopping_session_id=other_session.id,
            )
            is None
        )
    finally:
        db.close()


def test_repository_rolls_back_when_update_commit_fails() -> None:
    db = Mock(spec=Session)
    db.execute.return_value.first.return_value = None
    db.commit.side_effect = RuntimeError("database unavailable")
    repository = GroceryItemRepository(db)
    item = GroceryItem(name="Rice", shopping_session_id=uuid4())

    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.update(
            item,
            household_id=uuid4(),
            actor_user_id=uuid4(),
        )

    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()


def test_repository_completes_pending_item_with_actor_and_timestamp() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="complete")
        repository = GroceryItemRepository(db)
        item = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Rice",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        completed_at = datetime.now(UTC).replace(microsecond=0)

        completed = repository.complete(
            item,
            household_id=shopping_session.household_id,
            completed_by_user_id=user.id,
            completed_at=completed_at,
        )

        assert completed.status == GroceryItemStatus.COMPLETED
        assert completed.completed_by_user_id == user.id
        assert completed.completed_at is not None
        assert completed.completed_at.replace(tzinfo=UTC) == completed_at
    finally:
        db.close()


def test_repository_complete_is_idempotent_and_preserves_original_details() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="complete-repeat")
        other_user, _ = create_dependencies(db, suffix="complete-repeat-other")
        repository = GroceryItemRepository(db)
        item = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Milk",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        original_time = datetime.now(UTC).replace(microsecond=0)
        repository.complete(
            item,
            household_id=shopping_session.household_id,
            completed_by_user_id=user.id,
            completed_at=original_time,
        )

        repeated = repository.complete(
            item,
            household_id=shopping_session.household_id,
            completed_by_user_id=other_user.id,
            completed_at=original_time + timedelta(minutes=5),
        )

        assert repeated.completed_by_user_id == user.id
        assert repeated.completed_at is not None
        assert repeated.completed_at.replace(tzinfo=UTC) == original_time
    finally:
        db.close()


def test_repository_reopens_completed_item_and_is_idempotent() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="reopen")
        repository = GroceryItemRepository(db)
        item = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Milk",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        repository.complete(
            item,
            household_id=shopping_session.household_id,
            completed_by_user_id=user.id,
        )

        reopened = repository.reopen(
            item,
            household_id=shopping_session.household_id,
            actor_user_id=user.id,
        )
        repeated = repository.reopen(
            reopened,
            household_id=shopping_session.household_id,
            actor_user_id=user.id,
        )

        assert repeated.status == GroceryItemStatus.PENDING
        assert repeated.completed_by_user_id is None
        assert repeated.completed_at is None
    finally:
        db.close()


def test_repository_rejects_rename_and_reopen_pending_duplicates() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="mutation-duplicate")
        repository = GroceryItemRepository(db)
        rice = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Rice",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        milk = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Milk",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        household_id = shopping_session.household_id
        actor_user_id = user.id

        milk.name = " RICE "
        with pytest.raises(DuplicatePendingGroceryItemError):
            repository.update(
                milk,
                household_id=household_id,
                actor_user_id=actor_user_id,
            )

        db.refresh(milk)
        assert milk.name == "Milk"

        repository.complete(
            rice,
            household_id=household_id,
            completed_by_user_id=actor_user_id,
        )
        replacement = repository.create(
            household_id=household_id,
            shopping_session_id=shopping_session.id,
            name="rice",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=actor_user_id,
            assigned_to_user_id=None,
        )

        with pytest.raises(DuplicatePendingGroceryItemError):
            repository.reopen(
                rice,
                household_id=household_id,
                actor_user_id=actor_user_id,
            )

        db.refresh(rice)
        assert rice.status == GroceryItemStatus.COMPLETED
        assert replacement.status == GroceryItemStatus.PENDING
    finally:
        db.close()


@pytest.mark.parametrize("operation", ["complete", "reopen"])
def test_repository_rolls_back_when_transition_execution_fails(
    operation: str,
) -> None:
    db = Mock(spec=Session)
    db.execute.side_effect = RuntimeError("database unavailable")
    repository = GroceryItemRepository(db)
    item = GroceryItem(id=uuid4(), name="Rice", shopping_session_id=uuid4())

    with pytest.raises(RuntimeError, match="database unavailable"):
        if operation == "complete":
            repository.complete(
                item,
                household_id=uuid4(),
                completed_by_user_id=uuid4(),
            )
        else:
            repository.reopen(
                item,
                household_id=uuid4(),
                actor_user_id=uuid4(),
            )

    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()


def test_repository_permanently_deletes_item() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_dependencies(db, suffix="delete")
        repository = GroceryItemRepository(db)
        item = repository.create(
            household_id=shopping_session.household_id,
            shopping_session_id=shopping_session.id,
            name="Rice",
            quantity=None,
            unit=None,
            notes=None,
            created_by_user_id=user.id,
            assigned_to_user_id=None,
        )
        item_id = item.id

        repository.delete(
            item,
            household_id=shopping_session.household_id,
            actor_user_id=user.id,
        )

        assert db.get(GroceryItem, item_id) is None
        assert (
            repository.get_for_session(
                item_id=item_id,
                shopping_session_id=shopping_session.id,
            )
            is None
        )
    finally:
        db.close()


def test_repository_rolls_back_when_delete_commit_fails() -> None:
    db = Mock(spec=Session)
    db.commit.side_effect = RuntimeError("database unavailable")
    repository = GroceryItemRepository(db)
    item = GroceryItem(id=uuid4(), name="Rice", shopping_session_id=uuid4())

    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.delete(
            item,
            household_id=uuid4(),
            actor_user_id=uuid4(),
        )

    db.delete.assert_called_once_with(item)
    db.rollback.assert_called_once_with()
