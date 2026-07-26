from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import (
    GroceryActivityEvent,
    GroceryActivityType,
    Household,
    ShoppingSession,
    User,
)
from app.repositories.grocery_activity_events import GroceryActivityEventRepository
from app.schemas.grocery_activity_events import GroceryActivityEventResponse


def create_test_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_dependencies(db: Session) -> tuple[User, Household, ShoppingSession]:
    user = User(
        email="activity-repository@example.com",
        display_name="Activity User",
        password_hash="!",
        preferred_language="en",
    )
    household = Household(name="Activity Household")
    db.add_all([user, household])
    db.flush()
    shopping_session = ShoppingSession(
        household_id=household.id,
        created_by_user_id=user.id,
    )
    db.add(shopping_session)
    db.commit()
    return user, household, shopping_session


def test_repository_lists_only_session_events_newest_first_with_limit() -> None:
    db = create_test_session()
    try:
        user, household, shopping_session = create_dependencies(db)
        other_session = ShoppingSession(
            household_id=household.id,
            created_by_user_id=user.id,
        )
        db.add(other_session)
        db.flush()
        now = datetime.now(UTC)
        older = GroceryActivityEvent(
            household_id=household.id,
            shopping_session_id=shopping_session.id,
            grocery_item_id=user.id,
            actor_user_id=user.id,
            event_type=GroceryActivityType.ITEM_ADDED,
            item_name="Rice",
            sequence_number=1,
            created_at=now - timedelta(minutes=2),
        )
        newer = GroceryActivityEvent(
            household_id=household.id,
            shopping_session_id=shopping_session.id,
            grocery_item_id=household.id,
            actor_user_id=user.id,
            event_type=GroceryActivityType.ITEM_EDITED,
            item_name="Brown rice",
            sequence_number=2,
            created_at=now,
        )
        hidden = GroceryActivityEvent(
            household_id=household.id,
            shopping_session_id=other_session.id,
            grocery_item_id=other_session.id,
            actor_user_id=user.id,
            event_type=GroceryActivityType.ITEM_ADDED,
            item_name="Hidden",
            sequence_number=1,
            created_at=now + timedelta(minutes=1),
        )
        db.add_all([older, newer, hidden])
        db.commit()

        events = GroceryActivityEventRepository(db).list_for_session(
            shopping_session.id,
            limit=1,
        )

        assert [event.id for event in events] == [newer.id]
    finally:
        db.close()


def test_activity_response_supports_deleted_item_snapshot_and_missing_actor() -> None:
    now = datetime.now(UTC)
    event = GroceryActivityEvent(
        id=uuid4(),
        household_id=uuid4(),
        shopping_session_id=uuid4(),
        grocery_item_id=uuid4(),
        actor_user_id=None,
        event_type=GroceryActivityType.ITEM_DELETED,
        item_name="Milk",
        sequence_number=5,
        created_at=now,
    )

    response = GroceryActivityEventResponse.model_validate(event)

    assert response.event_type == GroceryActivityType.ITEM_DELETED
    assert response.item_name == "Milk"
    assert response.sequence_number == 5
    assert response.actor_user_id is None
    assert response.created_at == now
