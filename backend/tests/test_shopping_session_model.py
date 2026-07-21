from sqlalchemy.orm import RelationshipProperty

from app.db.base import Base
from app.models import Household, ShoppingSession, ShoppingSessionStatus


def test_shopping_session_table_is_registered() -> None:
    assert "shopping_sessions" in Base.metadata.tables


def test_shopping_session_columns_define_the_session_lifecycle() -> None:
    columns = ShoppingSession.__table__.columns

    assert "id" in columns
    assert "household_id" in columns
    assert "created_by_user_id" in columns
    assert "status" in columns
    assert "created_at" in columns
    assert "completed_at" in columns

    assert columns["household_id"].nullable is False
    assert columns["created_by_user_id"].nullable is True
    assert columns["status"].nullable is False
    assert columns["completed_at"].nullable is True


def test_shopping_session_statuses_are_defined() -> None:
    assert ShoppingSessionStatus.ACTIVE == "active"
    assert ShoppingSessionStatus.COMPLETED == "completed"


def test_shopping_session_relationships_are_configured() -> None:
    assert isinstance(Household.shopping_sessions.property, RelationshipProperty)
    assert isinstance(ShoppingSession.household.property, RelationshipProperty)
