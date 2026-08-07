from datetime import UTC, datetime
from uuid import UUID

from app.models.grocery_activity_event import GroceryActivityEvent
from app.models.grocery_item import GroceryItem, GroceryItemStatus
from app.models.shopping_session import ShoppingSessionStatus
from app.models.user import User
from app.repositories.grocery_activity_events import GroceryActivityEventRepository
from app.repositories.grocery_items import (
    DuplicatePendingGroceryItemError,
    GroceryItemRepository,
)
from app.repositories.grocery_mutation_idempotency import (
    DuplicateGroceryMutationIdempotencyError,
    GroceryMutationIdempotencyContext,
    GroceryMutationIdempotencyRepository,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import ShoppingSessionRepository
from app.schemas.grocery_items import CreateGroceryItemRequest, UpdateGroceryItemRequest


class GroceryItemShoppingSessionNotFoundError(ValueError):
    pass


class GroceryItemShoppingSessionCompletedError(ValueError):
    pass


class GroceryItemAssigneeNotFoundError(ValueError):
    pass


class GroceryItemNotFoundError(ValueError):
    pass


class GroceryItemCompletedError(ValueError):
    pass


class GroceryItemDuplicateError(ValueError):
    pass


class GroceryItemVersionConflictError(ValueError):
    pass


def _normalized_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _ensure_item_version(
    item: GroceryItem,
    expected_updated_at: datetime | None,
    item_repository: GroceryItemRepository,
    idempotency_context: GroceryMutationIdempotencyContext | None,
) -> None:
    if expected_updated_at is None:
        return
    if _normalized_utc(item.updated_at) != _normalized_utc(expected_updated_at):
        if (
            idempotency_context is not None
            and GroceryMutationIdempotencyRepository(item_repository.db).get(
                idempotency_context.mutation_id,
            )
            is not None
        ):
            raise DuplicateGroceryMutationIdempotencyError
        raise GroceryItemVersionConflictError


def create_grocery_item(
    household_id: UUID,
    session_id: UUID,
    data: CreateGroceryItemRequest,
    user: User,
    item_repository: GroceryItemRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    *,
    idempotency_context: GroceryMutationIdempotencyContext | None = None,
) -> GroceryItem:
    user_ids = {user.id}
    if data.assigned_to_user_id is not None:
        user_ids.add(data.assigned_to_user_id)

    memberships = member_repository.lock_for_users(
        household_id=household_id,
        user_ids=user_ids,
    )
    if user.id not in memberships:
        raise GroceryItemShoppingSessionNotFoundError
    if (
        data.assigned_to_user_id is not None
        and data.assigned_to_user_id not in memberships
    ):
        raise GroceryItemAssigneeNotFoundError

    shopping_session = session_repository.get_for_household_for_update(
        session_id=session_id,
        household_id=household_id,
    )
    if shopping_session is None:
        raise GroceryItemShoppingSessionNotFoundError
    if shopping_session.status != ShoppingSessionStatus.ACTIVE:
        raise GroceryItemShoppingSessionCompletedError

    try:
        if idempotency_context is None:
            return item_repository.create(
                household_id=household_id,
                shopping_session_id=shopping_session.id,
                name=data.name,
                quantity=data.quantity,
                unit=data.unit,
                notes=data.notes,
                created_by_user_id=user.id,
                assigned_to_user_id=data.assigned_to_user_id,
            )
        return item_repository.create(
            household_id=household_id,
            shopping_session_id=shopping_session.id,
            name=data.name,
            quantity=data.quantity,
            unit=data.unit,
            notes=data.notes,
            created_by_user_id=user.id,
            assigned_to_user_id=data.assigned_to_user_id,
            idempotency_context=idempotency_context,
        )
    except DuplicatePendingGroceryItemError as error:
        raise GroceryItemDuplicateError from error


def list_grocery_items(
    household_id: UUID,
    session_id: UUID,
    user: User,
    item_repository: GroceryItemRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
) -> list[GroceryItem]:
    membership = member_repository.get_for_user_and_household(
        user_id=user.id,
        household_id=household_id,
    )
    if membership is None:
        raise GroceryItemShoppingSessionNotFoundError

    shopping_session = session_repository.get_for_household(
        session_id=session_id,
        household_id=household_id,
    )
    if shopping_session is None:
        raise GroceryItemShoppingSessionNotFoundError

    return item_repository.list_for_session(shopping_session.id)


def update_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    data: UpdateGroceryItemRequest,
    user: User,
    item_repository: GroceryItemRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    *,
    expected_updated_at: datetime | None = None,
    idempotency_context: GroceryMutationIdempotencyContext | None = None,
) -> GroceryItem:
    memberships = member_repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id},
    )
    if user.id not in memberships:
        raise GroceryItemNotFoundError

    shopping_session = session_repository.get_for_household_for_update(
        session_id=session_id,
        household_id=household_id,
    )
    if shopping_session is None:
        raise GroceryItemNotFoundError
    if shopping_session.status != ShoppingSessionStatus.ACTIVE:
        raise GroceryItemShoppingSessionCompletedError

    item = item_repository.get_for_session_for_update(
        item_id=item_id,
        shopping_session_id=shopping_session.id,
    )
    if item is None:
        raise GroceryItemNotFoundError
    _ensure_item_version(
        item,
        expected_updated_at,
        item_repository,
        idempotency_context,
    )
    if item.status != GroceryItemStatus.PENDING:
        raise GroceryItemCompletedError

    changes = data.model_dump(exclude_unset=True)
    assignee_id = changes.get("assigned_to_user_id")
    if assignee_id is not None:
        assignee_memberships = member_repository.lock_for_users(
            household_id=household_id,
            user_ids={assignee_id},
        )
        if assignee_id not in assignee_memberships:
            raise GroceryItemAssigneeNotFoundError

    for field, value in changes.items():
        setattr(item, field, value)

    try:
        if idempotency_context is None:
            return item_repository.update(
                item,
                household_id=household_id,
                actor_user_id=user.id,
            )
        return item_repository.update(
            item,
            household_id=household_id,
            actor_user_id=user.id,
            idempotency_context=idempotency_context,
        )
    except DuplicatePendingGroceryItemError as error:
        raise GroceryItemDuplicateError from error


def _get_item_for_active_session(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    user: User,
    item_repository: GroceryItemRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    expected_updated_at: datetime | None = None,
    idempotency_context: GroceryMutationIdempotencyContext | None = None,
) -> GroceryItem:
    memberships = member_repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id},
    )
    if user.id not in memberships:
        raise GroceryItemNotFoundError

    shopping_session = session_repository.get_for_household_for_update(
        session_id=session_id,
        household_id=household_id,
    )
    if shopping_session is None:
        raise GroceryItemNotFoundError
    if shopping_session.status != ShoppingSessionStatus.ACTIVE:
        raise GroceryItemShoppingSessionCompletedError

    item = item_repository.get_for_session_for_update(
        item_id=item_id,
        shopping_session_id=shopping_session.id,
    )
    if item is None:
        raise GroceryItemNotFoundError
    _ensure_item_version(
        item,
        expected_updated_at,
        item_repository,
        idempotency_context,
    )
    return item


def complete_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    user: User,
    item_repository: GroceryItemRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    *,
    completed_at: datetime | None = None,
    expected_updated_at: datetime | None = None,
    idempotency_context: GroceryMutationIdempotencyContext | None = None,
) -> GroceryItem:
    item = _get_item_for_active_session(
        household_id,
        session_id,
        item_id,
        user,
        item_repository,
        session_repository,
        member_repository,
        expected_updated_at,
        idempotency_context,
    )
    if idempotency_context is None:
        return item_repository.complete(
            item,
            household_id=household_id,
            completed_by_user_id=user.id,
            completed_at=completed_at,
        )
    return item_repository.complete(
        item,
        household_id=household_id,
        completed_by_user_id=user.id,
        completed_at=completed_at,
        idempotency_context=idempotency_context,
    )


def reopen_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    user: User,
    item_repository: GroceryItemRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    *,
    expected_updated_at: datetime | None = None,
    idempotency_context: GroceryMutationIdempotencyContext | None = None,
) -> GroceryItem:
    item = _get_item_for_active_session(
        household_id,
        session_id,
        item_id,
        user,
        item_repository,
        session_repository,
        member_repository,
        expected_updated_at,
        idempotency_context,
    )
    try:
        if idempotency_context is None:
            return item_repository.reopen(
                item,
                household_id=household_id,
                actor_user_id=user.id,
            )
        return item_repository.reopen(
            item,
            household_id=household_id,
            actor_user_id=user.id,
            idempotency_context=idempotency_context,
        )
    except DuplicatePendingGroceryItemError as error:
        raise GroceryItemDuplicateError from error


def delete_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    user: User,
    item_repository: GroceryItemRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    *,
    expected_updated_at: datetime | None = None,
    idempotency_context: GroceryMutationIdempotencyContext | None = None,
) -> None:
    item = _get_item_for_active_session(
        household_id,
        session_id,
        item_id,
        user,
        item_repository,
        session_repository,
        member_repository,
        expected_updated_at,
        idempotency_context,
    )
    if item.status != GroceryItemStatus.PENDING:
        raise GroceryItemCompletedError

    if idempotency_context is None:
        item_repository.delete(
            item,
            household_id=household_id,
            actor_user_id=user.id,
        )
        return
    item_repository.delete(
        item,
        household_id=household_id,
        actor_user_id=user.id,
        idempotency_context=idempotency_context,
    )


def list_grocery_activity_events(
    household_id: UUID,
    session_id: UUID,
    user: User,
    event_repository: GroceryActivityEventRepository,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    *,
    limit: int,
) -> list[GroceryActivityEvent]:
    membership = member_repository.get_for_user_and_household(
        user_id=user.id,
        household_id=household_id,
    )
    if membership is None:
        raise GroceryItemShoppingSessionNotFoundError

    shopping_session = session_repository.get_for_household(
        session_id=session_id,
        household_id=household_id,
    )
    if shopping_session is None:
        raise GroceryItemShoppingSessionNotFoundError

    return event_repository.list_for_session(
        shopping_session.id,
        limit=limit,
    )
