from datetime import datetime
from uuid import UUID

from app.models.shopping_session import ShoppingSession
from app.models.user import User
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import (
    ShoppingSessionNotActiveError,
    ShoppingSessionRepository,
)


class ShoppingSessionHouseholdNotFoundError(ValueError):
    pass


class ShoppingSessionNotFoundError(ValueError):
    pass


class ActiveShoppingSessionExistsError(ValueError):
    pass


def create_shopping_session(
    household_id: UUID,
    user: User,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
) -> ShoppingSession:
    memberships = member_repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id},
    )
    if user.id not in memberships:
        raise ShoppingSessionHouseholdNotFoundError

    if not session_repository.lock_household(household_id):
        raise ShoppingSessionHouseholdNotFoundError

    if session_repository.get_active_for_household(household_id) is not None:
        raise ActiveShoppingSessionExistsError

    return session_repository.create(
        household_id=household_id,
        created_by_user_id=user.id,
    )


def list_shopping_sessions(
    household_id: UUID,
    user: User,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
) -> list[ShoppingSession]:
    membership = member_repository.get_for_user_and_household(
        user_id=user.id,
        household_id=household_id,
    )
    if membership is None:
        raise ShoppingSessionHouseholdNotFoundError

    return session_repository.list_for_household(household_id)


def get_shopping_session(
    household_id: UUID,
    session_id: UUID,
    user: User,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
) -> ShoppingSession:
    membership = member_repository.get_for_user_and_household(
        user_id=user.id,
        household_id=household_id,
    )
    if membership is None:
        raise ShoppingSessionNotFoundError

    shopping_session = session_repository.get_for_household(
        session_id=session_id,
        household_id=household_id,
    )
    if shopping_session is None:
        raise ShoppingSessionNotFoundError

    return shopping_session


def complete_shopping_session(
    household_id: UUID,
    session_id: UUID,
    user: User,
    session_repository: ShoppingSessionRepository,
    member_repository: HouseholdMemberRepository,
    *,
    completed_at: datetime | None = None,
) -> ShoppingSession:
    memberships = member_repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id},
    )
    if user.id not in memberships:
        raise ShoppingSessionNotFoundError

    shopping_session = session_repository.get_for_household(
        session_id=session_id,
        household_id=household_id,
    )
    if shopping_session is None:
        raise ShoppingSessionNotFoundError

    try:
        return session_repository.complete(
            shopping_session,
            completed_at=completed_at,
        )
    except ShoppingSessionNotActiveError as error:
        raise ShoppingSessionNotFoundError from error
