from uuid import UUID

from app.core.security import InvalidTokenError, TokenType, decode_token
from app.models.user import User
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.users import UserRepository


class RealtimeAuthenticationError(ValueError):
    pass


class RealtimeHouseholdNotFoundError(ValueError):
    pass


def authenticate_realtime_connection(
    authorization_header: str | None,
    household_id: UUID,
    user_repository: UserRepository,
    member_repository: HouseholdMemberRepository,
) -> User:
    token = _extract_bearer_token(authorization_header)
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
    except InvalidTokenError as error:
        raise RealtimeAuthenticationError from error

    user = user_repository.get_by_id(payload.subject)
    if user is None or not user.is_active:
        raise RealtimeAuthenticationError

    membership = member_repository.get_for_user_and_household(
        user_id=user.id,
        household_id=household_id,
    )
    if membership is None:
        raise RealtimeHouseholdNotFoundError

    return user


def _extract_bearer_token(authorization_header: str | None) -> str:
    if authorization_header is None:
        raise RealtimeAuthenticationError

    parts = authorization_header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise RealtimeAuthenticationError

    return parts[1]
