from app.core.security import verify_password
from app.models.user import User
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.users import UserRepository
from app.schemas.users import DeleteUserAccountRequest, UpdateUserProfileRequest


class IncorrectPasswordError(ValueError):
    pass


class HouseholdOwnershipError(ValueError):
    pass


def update_user_profile(
    user: User,
    data: UpdateUserProfileRequest,
    repository: UserRepository,
) -> User:
    if data.display_name is not None:
        user.display_name = data.display_name
    if data.preferred_language is not None:
        user.preferred_language = data.preferred_language

    return repository.update(user)


def delete_user_account(
    user: User,
    data: DeleteUserAccountRequest,
    user_repository: UserRepository,
    household_member_repository: HouseholdMemberRepository,
) -> None:
    if not verify_password(data.password, user.password_hash):
        raise IncorrectPasswordError

    if household_member_repository.user_owns_household(user.id):
        raise HouseholdOwnershipError

    user_repository.delete(user)
