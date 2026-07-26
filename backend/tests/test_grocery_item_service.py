from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.models import (
    GroceryItem,
    GroceryItemStatus,
    HouseholdMember,
    HouseholdRole,
    ShoppingSession,
    ShoppingSessionStatus,
    User,
)
from app.repositories.grocery_items import GroceryItemRepository
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import ShoppingSessionRepository
from app.schemas.grocery_items import CreateGroceryItemRequest, UpdateGroceryItemRequest
from app.services.grocery_items import (
    GroceryItemAssigneeNotFoundError,
    GroceryItemCompletedError,
    GroceryItemNotFoundError,
    GroceryItemShoppingSessionCompletedError,
    GroceryItemShoppingSessionNotFoundError,
    complete_grocery_item,
    create_grocery_item,
    delete_grocery_item,
    list_grocery_items,
    reopen_grocery_item,
    update_grocery_item,
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
        status=GroceryItemStatus.PENDING,
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


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_member_can_update_pending_item(role: HouseholdRole) -> None:
    user = build_user()
    assignee = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    item = build_item(shopping_session.id, user.id)
    data = UpdateGroceryItemRequest(
        name="Brown rice",
        quantity=Decimal("2.500"),
        assigned_to_user_id=assignee.id,
    )
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.side_effect = [
        {user.id: build_membership(user.id, household_id, role=role)},
        {assignee.id: build_membership(assignee.id, household_id)},
    ]
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item
    item_repository.update.return_value = item

    result = update_grocery_item(
        household_id,
        shopping_session.id,
        item.id,
        data,
        user,
        item_repository,
        session_repository,
        member_repository,
    )

    assert result is item
    assert item.name == "Brown rice"
    assert item.quantity == Decimal("2.500")
    assert item.assigned_to_user_id == assignee.id
    item_repository.update.assert_called_once_with(item)


def test_update_can_clear_optional_item_fields() -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    item = build_item(shopping_session.id, user.id)
    item.quantity = Decimal("5")
    item.unit = "kg"
    item.notes = "Old note"
    item.assigned_to_user_id = user.id
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item
    item_repository.update.return_value = item

    update_grocery_item(
        household_id,
        shopping_session.id,
        item.id,
        UpdateGroceryItemRequest(
            quantity=None,
            unit=None,
            notes=None,
            assigned_to_user_id=None,
        ),
        user,
        item_repository,
        session_repository,
        member_repository,
    )

    assert item.quantity is None
    assert item.unit is None
    assert item.notes is None
    assert item.assigned_to_user_id is None


def test_outsider_cannot_update_or_discover_item() -> None:
    user = build_user()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {}
    session_repository = Mock(spec=ShoppingSessionRepository)
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemNotFoundError):
        update_grocery_item(
            uuid4(),
            uuid4(),
            uuid4(),
            UpdateGroceryItemRequest(name="Hidden"),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    session_repository.get_for_household_for_update.assert_not_called()
    item_repository.get_for_session_for_update.assert_not_called()


@pytest.mark.parametrize(
    ("session_status", "item_status", "expected_error"),
    [
        (None, GroceryItemStatus.PENDING, GroceryItemNotFoundError),
        (
            ShoppingSessionStatus.COMPLETED,
            GroceryItemStatus.PENDING,
            GroceryItemShoppingSessionCompletedError,
        ),
        (
            ShoppingSessionStatus.ACTIVE,
            GroceryItemStatus.COMPLETED,
            GroceryItemCompletedError,
        ),
    ],
)
def test_update_requires_active_session_and_pending_item(
    session_status: ShoppingSessionStatus | None,
    item_status: GroceryItemStatus,
    expected_error: type[ValueError],
) -> None:
    user = build_user()
    household_id = uuid4()
    session_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    shopping_session = (
        build_session(household_id, status=session_status)
        if session_status is not None
        else None
    )
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item = build_item(session_id, user.id)
    item.status = item_status
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item

    with pytest.raises(expected_error):
        update_grocery_item(
            household_id,
            session_id,
            item.id,
            UpdateGroceryItemRequest(name="Updated"),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    item_repository.update.assert_not_called()


def test_update_rejects_assignee_outside_household() -> None:
    user = build_user()
    household_id = uuid4()
    outsider_id = uuid4()
    shopping_session = build_session(household_id)
    item = build_item(shopping_session.id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.side_effect = [
        {user.id: build_membership(user.id, household_id)},
        {},
    ]
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item

    with pytest.raises(GroceryItemAssigneeNotFoundError):
        update_grocery_item(
            household_id,
            shopping_session.id,
            item.id,
            UpdateGroceryItemRequest(assigned_to_user_id=outsider_id),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    item_repository.update.assert_not_called()


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_member_can_complete_item(role: HouseholdRole) -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    item = build_item(shopping_session.id, user.id)
    completed_at = datetime.now(UTC)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id, role=role),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item
    item_repository.complete.return_value = item

    result = complete_grocery_item(
        household_id,
        shopping_session.id,
        item.id,
        user,
        item_repository,
        session_repository,
        member_repository,
        completed_at=completed_at,
    )

    assert result is item
    item_repository.complete.assert_called_once_with(
        item,
        completed_by_user_id=user.id,
        completed_at=completed_at,
    )


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_member_can_reopen_item(role: HouseholdRole) -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    item = build_item(shopping_session.id, user.id)
    item.status = GroceryItemStatus.COMPLETED
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id, role=role),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item
    item_repository.reopen.return_value = item

    result = reopen_grocery_item(
        household_id,
        shopping_session.id,
        item.id,
        user,
        item_repository,
        session_repository,
        member_repository,
    )

    assert result is item
    item_repository.reopen.assert_called_once_with(item)


@pytest.mark.parametrize("operation", [complete_grocery_item, reopen_grocery_item])
def test_outsider_cannot_transition_or_discover_item(operation: object) -> None:
    user = build_user()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {}
    session_repository = Mock(spec=ShoppingSessionRepository)
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemNotFoundError):
        operation(  # type: ignore[operator]
            uuid4(),
            uuid4(),
            uuid4(),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    session_repository.get_for_household_for_update.assert_not_called()
    item_repository.get_for_session_for_update.assert_not_called()


@pytest.mark.parametrize("operation", [complete_grocery_item, reopen_grocery_item])
def test_completed_session_rejects_item_transition(operation: object) -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(
        household_id,
        status=ShoppingSessionStatus.COMPLETED,
    )
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemShoppingSessionCompletedError):
        operation(  # type: ignore[operator]
            household_id,
            shopping_session.id,
            uuid4(),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    item_repository.get_for_session_for_update.assert_not_called()


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_member_can_delete_pending_item(role: HouseholdRole) -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    item = build_item(shopping_session.id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id, role=role),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item

    delete_grocery_item(
        household_id,
        shopping_session.id,
        item.id,
        user,
        item_repository,
        session_repository,
        member_repository,
    )

    item_repository.delete.assert_called_once_with(item)


def test_outsider_cannot_delete_or_discover_item() -> None:
    user = build_user()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {}
    session_repository = Mock(spec=ShoppingSessionRepository)
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemNotFoundError):
        delete_grocery_item(
            uuid4(),
            uuid4(),
            uuid4(),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    session_repository.get_for_household_for_update.assert_not_called()
    item_repository.delete.assert_not_called()


def test_completed_session_rejects_item_deletion() -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(
        household_id,
        status=ShoppingSessionStatus.COMPLETED,
    )
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)

    with pytest.raises(GroceryItemShoppingSessionCompletedError):
        delete_grocery_item(
            household_id,
            shopping_session.id,
            uuid4(),
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    item_repository.get_for_session_for_update.assert_not_called()
    item_repository.delete.assert_not_called()


def test_completed_item_must_be_reopened_before_deletion() -> None:
    user = build_user()
    household_id = uuid4()
    shopping_session = build_session(household_id)
    item = build_item(shopping_session.id, user.id)
    item.status = GroceryItemStatus.COMPLETED
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    session_repository = Mock(spec=ShoppingSessionRepository)
    session_repository.get_for_household_for_update.return_value = shopping_session
    item_repository = Mock(spec=GroceryItemRepository)
    item_repository.get_for_session_for_update.return_value = item

    with pytest.raises(GroceryItemCompletedError):
        delete_grocery_item(
            household_id,
            shopping_session.id,
            item.id,
            user,
            item_repository,
            session_repository,
            member_repository,
        )

    item_repository.delete.assert_not_called()
