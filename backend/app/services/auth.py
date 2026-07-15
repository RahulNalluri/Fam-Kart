from app.core.security import hash_password
from app.models.user import User
from app.repositories.users import DuplicateUserEmailError, UserRepository
from app.schemas.auth import RegisterRequest


class EmailAlreadyRegisteredError(ValueError):
    pass


def register_user(data: RegisterRequest, repository: UserRepository) -> User:
    if repository.get_by_email(str(data.email)) is not None:
        raise EmailAlreadyRegisteredError

    user = User(
        email=str(data.email),
        display_name=data.display_name,
        password_hash=hash_password(data.password),
        preferred_language=data.preferred_language,
    )

    try:
        return repository.create(user)
    except DuplicateUserEmailError as error:
        raise EmailAlreadyRegisteredError from error
