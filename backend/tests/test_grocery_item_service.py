from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.models import (
    GroceryItem,
    HouseholdMember,
    HouseholdRole,
    ShoppingSession,
    ShoppingSessionStatus,
    User,
)
from app.repositories.grocery_items import GroceryItemRepository
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import ShoppingSessionRepository
from app.schemas.grocery_items import CreateGroceryItemRequest
from app.services.grocery_items import (
    GroceryItemAssigneeNotFoundError,
    GroceryItemShoppingSessionCompletedError,
    GroceryItemShoppingSessionNotFoundError,
    create_grocery_item,
    list_grocery_items,
)


def build_user() -> User:
    return User(
        id=uuid4(),
        email="grocery-service@example.com",
        display_name="Grocery Service User",
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


def build_session(
    household_id: UUID,
    *,
    status: ShoppingSessionStatus = ShoppingSessionStatus.ACTIVE,
) -> ShoppingSession:
    return ShoppingSession(
        id=uuid4(),
        household_id=household_id,
        status=status,
    )


def build_item(session_id: UUID, user_id: UUID) -> GroceryItem:
    return GroceryItem(
        id=uuid4(),
        shopping_session_id=session_id,
        name="Rice",
        created_by_user_id=user_id,
    )


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_member_can_create_unassigned_item(role: HouseholdRole) -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    data = CreateGroceryItemRequest(
        name="Rice",
        quantity=Decimal("5"),
        unit="kg",
    )
    expected = build_item(shopping_session.id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id, role=role),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.create.return_value = expected

    result = create_grocery_item(
        household_id,
        shopping_session.id,
        data,
        user,
        item_repository,
        session_repository,
        member_repository,
    )

    assert result is expected
    member_repository.lock_for_users.assert_called_once_with(
        household_id=household_id,
        user_ids={user.id},
    )
    item_repository.create.assert_called_once_with(
        shopping_session_id=shopping_session.id,
        name="Rice",
        quantity=Decimal("5"),
        unit="kg",
        notes=None,
        created_by_user_id=user.id,
        assigned_to_user_id=None,
    )


def test_member_can_assign_new_item_to_current_household_member() -> None:
    user = build_user()
    assignee = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    data = CreateGroceryItemRequest(
        name="Milk",
        assigned_to_user_id=assignee.id,
    )
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
        assignee.id: build_membership(assignee.id, household_id),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.create.return_value = build_item(shopping_session.id, user.id)

    create_grocery_item(
        household_id,
        shopping_session.id,
        data,
        user,
        item_repository,
        session_repository,
        member_repository,
    )

    member_repository.lock_for_users.assert_called_once_with(
        household_id=household_id,
        user_ids={user.id, assignee.id},
    )
    assert item_repository.create.call_args.kwargs["assigned_to_user_id"] == (
        assignee.id
    )


def test_outsider_cannot_create_or_discover_item_session() -> None:
    user = build_user()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {}
    session_repository = Mock(spec=ShoppingSessionRepository)
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemShoppingSessionNotFoundError):
        create_grocery_item(
            uuid4(),
            uuid4(),
            CreateGroceryItemRequest(name="Rice"),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    session_repository.get_for_household_for_update.assert_not_called()
    item_repository.create.assert_not_called()


def test_item_cannot_be_assigned_to_outsider() -> None:
    user = build_user()
    household_id = uuid4()
    outsider_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemAssigneeNotFoundError):
        create_grocery_item(
            household_id,
            uuid4(),
            CreateGroceryItemRequest(
                name="Rice",
                assigned_to_user_id=outsider_id,
            ),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    session_repository.get_for_household_for_update.assert_not_called()
    item_repository.create.assert_not_called()


@pytest.mark.parametrize(
    ("session_status", "expected_error"),
    [
        (None, GroceryItemShoppingSessionNotFoundError),
        (
            ShoppingSessionStatus.COMPLETED,
            GroceryItemShoppingSessionCompletedError,
        ),
    ],
)
def test_item_creation_requires_active_scoped_session(
    session_status: ShoppingSessionStatus | None,
    expected_error: type[ValueError],
) -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = (
        build_session(household_id, status=session_status)
        if session_status is not None
        else None
    )
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(expected_error):
        create_grocery_item(
            household_id,
            uuid4(),
            CreateGroceryItemRequest(name="Rice"),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    item_repository.create.assert_not_called()


@pytest.mark.parametrize(
    "session_status",
    [ShoppingSessionStatus.ACTIVE, ShoppingSessionStatus.COMPLETED],
)
def test_member_can_list_items_from_active_or_completed_session(
    session_status: ShoppingSessionStatus,
) -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id, status=session_status)
    expected = [build_item(shopping_session.id, user.id)]
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = build_membership(
        user.id,
        household_id,
    )
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.list_for_session.return_value = expected

    result = list_grocery_items(
        household_id,
        shopping_session.id,
        user,
        item_repository,
        session_repository,
        member_repository,
    )

    assert result is expected
    item_repository.list_for_session.assert_called_once_with(shopping_session.id)


@pytest.mark.parametrize("has_membership", [False, True])
def test_outsider_or_unknown_session_cannot_list_items(
    has_membership: bool,
) -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = (
        build_membership(user.id, household_id) if has_membership else None
    )
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household.return_value = None
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemShoppingSessionNotFoundError):
        list_grocery_items(
            household_id,
            uuid4(),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    item_repository.list_for_session.assert_not_called()
    if has_membership:
        session_repository.get_for_household.assert_called_once()
    else:
        session_repository.get_for_household.assert_not_called()
