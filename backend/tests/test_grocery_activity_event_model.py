from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import GroceryActivityEvent, GroceryActivityType


def test_activity_event_model_defines_required_columns_and_indexes() -> None:
    columns = GroceryActivityEvent.__table__.columns

    assert set(columns.keys()) == {
        "id",
        "household_id",
        "shopping_session_id",
        "grocery_item_id",
        "actor_user_id",
        "event_type",
        "item_name",
        "sequence_number",
        "created_at",
    }
    index_names = {index.name for index in GroceryActivityEvent.__table__.indexes}
    assert "ix_grocery_activity_events_household_id_created_at" in index_names
    assert "ix_grocery_activity_events_session_id_created_at" in index_names
    assert "ix_grocery_activity_events_grocery_item_id" in index_names
    assert "ix_grocery_activity_events_actor_user_id" in index_names


def test_activity_type_contains_every_grocery_mutation() -> None:
    assert [event_type.value for event_type in GroceryActivityType] == [
        "item_added",
        "item_edited",
        "item_completed",
        "item_reopened",
        "item_deleted",
    ]


def test_database_rejects_blank_activity_item_snapshot() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as db:
            db.add(
                GroceryActivityEvent(
                    household_id=uuid4(),
                    shopping_session_id=uuid4(),
                    grocery_item_id=uuid4(),
                    actor_user_id=None,
                    event_type=GroceryActivityType.ITEM_DELETED,
                    item_name="   ",
                    sequence_number=1,
                    created_at=datetime.now(UTC),
                ),
            )
            with pytest.raises(IntegrityError):
                db.commit()
    finally:
        engine.dispose()
