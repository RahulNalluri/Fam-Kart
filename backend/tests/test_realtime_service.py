from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.security import create_access_token, create_refresh_token
from app.models import HouseholdMember, HouseholdRole, User
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.users import UserRepository
from app.services.realtime import (
    RealtimeAuthenticationError,
    RealtimeHouseholdNotFoundError,
    authenticate_realtime_connection,
)


def build_user(*, is_active: bool = True) -> User:
    return User(
        id=uuid4(),
        email="realtime-service@example.com",
        display_name="Realtime Service User",
        password_hash="!",
        preferred_language="en",
        is_active=is_active,
    )


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_active_household_member_is_authenticated(role: HouseholdRole) -> None:
    user = build_user()
    household_id = uuid4()
    user_repository = Mock(spec=UserRepository)
    user_repository.get_by_id.return_value = user
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = HouseholdMember(
        user_id=user.id,
        household_id=household_id,
        role=role,
    )

    result = authenticate_realtime_connection(
        f"bEaReR {create_access_token(user.id)}",
        household_id,
        user_repository,
        member_repository,
    )

    assert result is user
    user_repository.get_by_id.assert_called_once_with(user.id)
    member_repository.get_for_user_and_household.assert_called_once_with(
        user_id=user.id,
        household_id=household_id,
    )


@pytest.mark.parametrize(
    "authorization_header",
    [None, "", "Basic credentials", "Bearer", "Bearer token extra", "Bearer invalid"],
)
def test_missing_or_invalid_credentials_are_rejected(
    authorization_header: str | None,
) -> None:
    user_repository = Mock(spec=UserRepository)
    member_repository = Mock(spec=HouseholdMemberRepository)

    with pytest.raises(RealtimeAuthenticationError):
        authenticate_realtime_connection(
            authorization_header,
            uuid4(),
            user_repository,
            member_repository,
        )

    user_repository.get_by_id.assert_not_called()
    member_repository.get_for_user_and_household.assert_not_called()


def test_refresh_token_is_rejected() -> None:
    user_repository = Mock(spec=UserRepository)
    member_repository = Mock(spec=HouseholdMemberRepository)

    with pytest.raises(RealtimeAuthenticationError):
        authenticate_realtime_connection(
            f"Bearer {create_refresh_token(uuid4())}",
            uuid4(),
            user_repository,
            member_repository,
        )

    user_repository.get_by_id.assert_not_called()


@pytest.mark.parametrize("user", [None, build_user(is_active=False)])
def test_missing_or_inactive_user_is_rejected(user: User | None) -> None:
    user_id = uuid4()
    user_repository = Mock(spec=UserRepository)
    user_repository.get_by_id.return_value = user
    member_repository = Mock(spec=HouseholdMemberRepository)

    with pytest.raises(RealtimeAuthenticationError):
        authenticate_realtime_connection(
            f"Bearer {create_access_token(user_id)}",
            uuid4(),
            user_repository,
            member_repository,
        )

    member_repository.get_for_user_and_household.assert_not_called()


def test_user_outside_household_receives_private_not_found_error() -> None:
    user = build_user()
    user_repository = Mock(spec=UserRepository)
    user_repository.get_by_id.return_value = user
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = None

    with pytest.raises(RealtimeHouseholdNotFoundError):
        authenticate_realtime_connection(
            f"Bearer {create_access_token(user.id)}",
            uuid4(),
            user_repository,
            member_repository,
        )
