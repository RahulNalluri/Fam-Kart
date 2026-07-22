from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.models import HouseholdMember, HouseholdRole, ShoppingSession, User
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import ShoppingSessionRepository
from app.services.shopping_sessions import (
    ActiveShoppingSessionExistsError,
    ShoppingSessionHouseholdNotFoundError,
    ShoppingSessionNotFoundError,
    create_shopping_session,
    get_shopping_session,
    list_shopping_sessions,
)


def build_user() -> User:
    return User(
        id=uuid4(),
        email="shopping-service@example.com",
        display_name="Shopping Service User",
        password_hash="!",
        preferred_language="en",
    )


def build_membership(
    user_id: UUID,
    household_id: UUID,
    *,
    role: HouseholdRole = HouseholdRole.MEMBER,
) -> HouseholdMember:
    return HouseholdMember(
        id=uuid4(),
        user_id=user_id,
        household_id=household_id,
        role=role,
    )


def build_session(household_id: UUID, user_id: UUID) -> ShoppingSession:
    return ShoppingSession(
        id=uuid4(),
        household_id=household_id,
        created_by_user_id=user_id,
    )


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_member_can_create_session(role: HouseholdRole) -> None:
    user = build_user()
    household_id = uuid4()
    membership = build_membership(user.id, household_id, role=role)
    expected = build_session(household_id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {user.id: membership}
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.lock_household.return_value = True
    session_repository.get_active_for_household.return_value = None
    session_repository.create.return_value = expected

    result = create_shopping_session(
        household_id,
        user,
        session_repository,
        member_repository,
    )

    assert result is expected
    member_repository.lock_for_users.assert_called_once_with(
        household_id=household_id,
        user_ids={user.id},
    )
    session_repository.lock_household.assert_called_once_with(household_id)
    session_repository.create.assert_called_once_with(
        household_id=household_id,
        created_by_user_id=user.id,
    )


def test_outsider_cannot_create_or_discover_household_session() -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {}
    session_repository = Mock(spec=ShoppingSessionRepository)

    with pytest.raises(ShoppingSessionHouseholdNotFoundError):
        create_shopping_session(
            household_id,
            user,
            session_repository,
            member_repository,
        )

    session_repository.lock_household.assert_not_called()
    session_repository.get_active_for_household.assert_not_called()
    session_repository.create.assert_not_called()


def test_second_active_session_is_rejected() -> None:
    user = build_user()
    household_id = uuid4()
    membership = build_membership(user.id, household_id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {user.id: membership}
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.lock_household.return_value = True
    session_repository.get_active_for_household.return_value = build_session(
        household_id,
        user.id,
    )

    with pytest.raises(ActiveShoppingSessionExistsError):
        create_shopping_session(
            household_id,
            user,
            session_repository,
            member_repository,
        )

    session_repository.create.assert_not_called()


def test_member_can_list_household_sessions() -> None:
    user = build_user()
    household_id = uuid4()
    expected = [build_session(household_id, user.id)]
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = build_membership(
        user.id,
        household_id,
    )
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.list_for_household.return_value = expected

    result = list_shopping_sessions(
        household_id,
        user,
        session_repository,
        member_repository,
    )

    assert result is expected
    session_repository.list_for_household.assert_called_once_with(household_id)


def test_outsider_cannot_list_household_sessions() -> None:
    user = build_user()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = None
    session_repository = Mock(spec=ShoppingSessionRepository)

    with pytest.raises(ShoppingSessionHouseholdNotFoundError):
        list_shopping_sessions(
            uuid4(),
            user,
            session_repository,
            member_repository,
        )

    session_repository.list_for_household.assert_not_called()


def test_session_lookup_is_scoped_to_membership_and_household() -> None:
    user = build_user()
    household_id = uuid4()
    session_id = uuid4()
    expected = build_session(household_id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = build_membership(
        user.id,
        household_id,
    )
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household.return_value = expected

    result = get_shopping_session(
        household_id,
        session_id,
        user,
        session_repository,
        member_repository,
    )

    assert result is expected
    session_repository.get_for_household.assert_called_once_with(
        session_id=session_id,
        household_id=household_id,
    )


@pytest.mark.parametrize("has_membership", [False, True])
def test_hidden_or_unknown_session_returns_same_error(has_membership: bool) -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = (
        build_membership(user.id, household_id) if has_membership else None
    )
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household.return_value = None

    with pytest.raises(ShoppingSessionNotFoundError):
        get_shopping_session(
            household_id,
            uuid4(),
            user,
            session_repository,
            member_repository,
        )

    if has_membership:
        session_repository.get_for_household.assert_called_once()
    else:
        session_repository.get_for_household.assert_not_called()
