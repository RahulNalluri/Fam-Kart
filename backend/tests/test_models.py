from sqlalchemy.orm import RelationshipProperty

from app.db.base import Base
from app.models import (
    AuthSession,
    Household,
    HouseholdInvitation,
    HouseholdMember,
    HouseholdRole,
    User,
)


def test_initial_model_tables_are_registered() -> None:
    assert {
        "users",
        "households",
        "household_members",
        "household_invitations",
        "auth_sessions",
    }.issubset(Base.metadata.tables)


def test_user_table_columns() -> None:
    columns = User.__table__.columns

    assert "id" in columns
    assert "email" in columns
    assert "display_name" in columns
    assert "password_hash" in columns
    assert "preferred_language" in columns
    assert "is_active" in columns
    assert "created_at" in columns
    assert "updated_at" in columns

    assert columns["password_hash"].nullable is False
    assert columns["password_hash"].type.length == 255


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


def test_auth_session_table_columns() -> None:
    columns = AuthSession.__table__.columns

    assert "id" in columns
    assert "user_id" in columns
    assert "refresh_token_hash" in columns
    assert "expires_at" in columns
    assert "revoked_at" in columns
    assert "created_at" in columns

    assert columns["user_id"].nullable is False
    assert columns["refresh_token_hash"].nullable is False
    assert columns["refresh_token_hash"].type.length == 64
    assert columns["expires_at"].nullable is False
    assert columns["revoked_at"].nullable is True


def test_household_invitation_table_columns() -> None:
    columns = HouseholdInvitation.__table__.columns

    assert "id" in columns
    assert "household_id" in columns
    assert "created_by_user_id" in columns
    assert "code_hash" in columns
    assert "expires_at" in columns
    assert "used_at" in columns
    assert "used_by_user_id" in columns
    assert "revoked_at" in columns
    assert "created_at" in columns

    assert columns["code_hash"].nullable is False
    assert columns["code_hash"].type.length == 64
    assert columns["expires_at"].nullable is False
    assert columns["used_at"].nullable is True
    assert columns["revoked_at"].nullable is True


def test_model_relationships_are_configured() -> None:
    assert isinstance(User.auth_sessions.property, RelationshipProperty)
    assert isinstance(AuthSession.user.property, RelationshipProperty)
    assert isinstance(User.household_memberships.property, RelationshipProperty)
    assert isinstance(Household.members.property, RelationshipProperty)
    assert isinstance(Household.invitations.property, RelationshipProperty)
    assert isinstance(HouseholdMember.user.property, RelationshipProperty)
    assert isinstance(HouseholdMember.household.property, RelationshipProperty)
    assert isinstance(HouseholdInvitation.household.property, RelationshipProperty)
