from sqlalchemy.orm import RelationshipProperty

from app.db.base import Base
from app.models import Household, HouseholdMember, HouseholdRole, User


def test_initial_model_tables_are_registered() -> None:
    assert {"users", "households", "household_members"}.issubset(
        Base.metadata.tables,
    )


def test_user_table_columns() -> None:
    columns = User.__table__.columns

    assert "id" in columns
    assert "email" in columns
    assert "display_name" in columns
    assert "preferred_language" in columns
    assert "is_active" in columns
    assert "created_at" in columns
    assert "updated_at" in columns


def test_household_table_columns() -> None:
    columns = Household.__table__.columns

    assert "id" in columns
    assert "name" in columns
    assert "created_at" in columns
    assert "updated_at" in columns


def test_household_member_table_columns() -> None:
    columns = HouseholdMember.__table__.columns

    assert "id" in columns
    assert "household_id" in columns
    assert "user_id" in columns
    assert "role" in columns
    assert "joined_at" in columns


def test_household_roles_are_defined() -> None:
    assert HouseholdRole.OWNER == "owner"
    assert HouseholdRole.MEMBER == "member"


def test_model_relationships_are_configured() -> None:
    assert isinstance(User.household_memberships.property, RelationshipProperty)
    assert isinstance(Household.members.property, RelationshipProperty)
    assert isinstance(HouseholdMember.user.property, RelationshipProperty)
    assert isinstance(HouseholdMember.household.property, RelationshipProperty)
