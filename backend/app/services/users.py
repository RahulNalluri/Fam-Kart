from app.models.user import User
from app.repositories.users import UserRepository
from app.schemas.users import UpdateUserProfileRequest


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
