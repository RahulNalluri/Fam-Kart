from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import RelationshipProperty, Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    GroceryItem,
    GroceryItemStatus,
    Household,
    ShoppingSession,
    User,
)


def create_test_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_item_dependencies(db: Session) -> tuple[User, ShoppingSession]:
    user = User(
        email="grocery-model@example.com",
        display_name="Grocery Model User",
        password_hash="!",
        preferred_language="en",
    )
    household = Household(name="Grocery Model Family")
    db.add_all([user, household])
    db.flush()
    shopping_session = ShoppingSession(
        household_id=household.id,
        created_by_user_id=user.id,
    )
    db.add(shopping_session)
    db.commit()
    return user, shopping_session


def test_grocery_item_table_is_registered() -> None:
    assert "grocery_items" in Base.metadata.tables


def test_grocery_item_columns_support_item_lifecycle() -> None:
    columns = GroceryItem.__table__.columns

    assert {
        "id",
        "shopping_session_id",
        "name",
        "quantity",
        "unit",
        "notes",
        "status",
        "created_by_user_id",
        "assigned_to_user_id",
        "completed_by_user_id",
        "created_at",
        "updated_at",
        "completed_at",
    } == set(columns.keys())
    assert columns["shopping_session_id"].nullable is False
    assert columns["name"].type.length == 160
    assert columns["quantity"].type.precision == 10
    assert columns["quantity"].type.scale == 3
    assert columns["status"].nullable is False
    assert columns["created_by_user_id"].nullable is True
    assert columns["assigned_to_user_id"].nullable is True
    assert columns["completed_by_user_id"].nullable is True
    assert columns["completed_at"].nullable is True


def test_grocery_item_statuses_are_defined() -> None:
    assert GroceryItemStatus.PENDING == "pending"
    assert GroceryItemStatus.COMPLETED == "completed"


def test_grocery_item_relationships_are_configured() -> None:
    assert isinstance(ShoppingSession.items.property, RelationshipProperty)
    assert isinstance(GroceryItem.shopping_session.property, RelationshipProperty)


def test_grocery_item_stores_multilingual_name_and_decimal_quantity() -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_item_dependencies(db)
        item = GroceryItem(
            shopping_session_id=shopping_session.id,
            name="Tomatoes - టమాటాలు",
            quantity=Decimal("2.500"),
            unit="kg",
            notes="Ripe",
            created_by_user_id=user.id,
            assigned_to_user_id=user.id,
        )
        db.add(item)
        db.commit()
        db.refresh(item)

        assert item.name == "Tomatoes - టమాటాలు"
        assert item.quantity == Decimal("2.500")
        assert item.status == GroceryItemStatus.PENDING
        assert item.completed_at is None
    finally:
        db.close()


@pytest.mark.parametrize(
    "item",
    [
        GroceryItem(name="   ", quantity=Decimal("1")),
        GroceryItem(name="Rice", quantity=Decimal("0")),
        GroceryItem(
            name="Milk",
            status=GroceryItemStatus.COMPLETED,
            completed_at=None,
        ),
        GroceryItem(
            name="Onions",
            status=GroceryItemStatus.PENDING,
            completed_at=datetime.now(UTC),
        ),
    ],
)
def test_database_rejects_invalid_grocery_item_state(item: GroceryItem) -> None:
    db = create_test_session()
    try:
        user, shopping_session = create_item_dependencies(db)
        item.shopping_session_id = shopping_session.id
        item.created_by_user_id = user.id
        db.add(item)

        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()
