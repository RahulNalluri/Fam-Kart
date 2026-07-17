from datetime import UTC, datetime, timedelta

from app.core.config import Settings, settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.models.user import User
from app.repositories.auth_sessions import (
    AuthSessionNotActiveError,
    AuthSessionRepository,
)
from app.repositories.users import DuplicateUserEmailError, UserRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
)

_DUMMY_PASSWORD_HASH = hash_password("familykart-dummy-password")


class EmailAlreadyRegisteredError(ValueError):
    pass


class InvalidCredentialsError(ValueError):
    pass


class InvalidRefreshTokenError(ValueError):
    pass


class InvalidLogoutTokenError(ValueError):
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


def refresh_tokens(
    data: RefreshTokenRequest,
    user_repository: UserRepository,
    session_repository: AuthSessionRepository,
    *,
    config: Settings = settings,
    now: datetime | None = None,
) -> TokenResponse:
    rotated_at = now or datetime.now(UTC)
    try:
        payload = decode_token(
            data.refresh_token,
            expected_type=TokenType.REFRESH,
            config=config,
        )
    except InvalidTokenError as error:
        raise InvalidRefreshTokenError from error

    auth_session = session_repository.get_by_refresh_token_hash(
        hash_refresh_token(data.refresh_token),
    )
    if auth_session is None or auth_session.user_id != payload.subject:
        raise InvalidRefreshTokenError

    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if auth_session.revoked_at is not None or expires_at <= rotated_at:
        raise InvalidRefreshTokenError

    user = user_repository.get_by_id(payload.subject)
    if user is None or not user.is_active:
        raise InvalidRefreshTokenError

    access_token = create_access_token(user.id, config=config, now=rotated_at)
    refresh_token = create_refresh_token(user.id, config=config, now=rotated_at)
    try:
        session_repository.rotate(
            auth_session,
            new_refresh_token_hash=hash_refresh_token(refresh_token),
            new_expires_at=rotated_at
            + timedelta(days=config.refresh_token_expire_days),
            rotated_at=rotated_at,
        )
    except AuthSessionNotActiveError as error:
        raise InvalidRefreshTokenError from error

    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        access_token_expires_in=config.access_token_expire_minutes * 60,
        refresh_token_expires_in=config.refresh_token_expire_days * 24 * 60 * 60,
    )


def logout_user(
    data: LogoutRequest,
    session_repository: AuthSessionRepository,
    *,
    config: Settings = settings,
    now: datetime | None = None,
) -> None:
    revoked_at = now or datetime.now(UTC)
    try:
        payload = decode_token(
            data.refresh_token,
            expected_type=TokenType.REFRESH,
            config=config,
        )
    except InvalidTokenError as error:
        raise InvalidLogoutTokenError from error

    auth_session = session_repository.get_by_refresh_token_hash(
        hash_refresh_token(data.refresh_token),
    )
    if auth_session is None or auth_session.user_id != payload.subject:
        raise InvalidLogoutTokenError

    expires_at = auth_session.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if auth_session.revoked_at is not None or expires_at <= revoked_at:
        raise InvalidLogoutTokenError

    try:
        session_repository.revoke(auth_session, revoked_at=revoked_at)
    except AuthSessionNotActiveError as error:
        raise InvalidLogoutTokenError from error
