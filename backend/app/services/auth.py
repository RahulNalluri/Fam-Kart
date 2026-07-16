from app.core.config import Settings, settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import User
from app.repositories.auth_sessions import AuthSessionRepository
from app.repositories.users import DuplicateUserEmailError, UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

_DUMMY_PASSWORD_HASH = hash_password("familykart-dummy-password")


class EmailAlreadyRegisteredError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
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


def login_user(
    data: LoginRequest,
    user_repository: UserRepository,
    session_repository: AuthSessionRepository,
    *,
    config: Settings = settings,
) -> TokenResponse:
    user = user_repository.get_by_email(str(data.email))

    if user is None:
        verify_password(data.password, _DUMMY_PASSWORD_HASH)
        raise InvalidCredentialsError

    if not verify_password(data.password, user.password_hash) or not user.is_active:
        raise InvalidCredentialsError

    access_token = create_access_token(user.id, config=config)
    refresh_token = create_refresh_token(user.id, config=config)
    refresh_payload = decode_token(
        refresh_token,
        expected_type=TokenType.REFRESH,
        config=config,
    )
    session_repository.create(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=refresh_payload.expires_at,
    )

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_in=config.access_token_expire_minutes * 60,
        refresh_token_expires_in=config.refresh_token_expire_days * 24 * 60 * 60,
    )
