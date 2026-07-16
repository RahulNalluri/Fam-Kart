from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.security import (
    TokenType,
    decode_token,
    hash_password,
    hash_refresh_token,
)
from app.models.user import User
from app.repositories.auth_sessions import AuthSessionRepository
from app.repositories.users import UserRepository
from app.schemas.auth import LoginRequest
from app.services.auth import InvalidCredentialsError, login_user


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="testing",
        jwt_secret_key="testing-jwt-secret-key-that-is-long-enough",
        access_token_expire_minutes=15,
        refresh_token_expire_days=30,
    )


def build_user(*, password: str = "familykart123", is_active: bool = True) -> User:
    return User(
        id=uuid4(),
        email="rahul@gmail.com",
        display_name="Rahul",
        password_hash=hash_password(password),
        preferred_language="en",
        is_active=is_active,
    )


def build_user_repository(user: User | None) -> Mock:
    repository = Mock(spec=UserRepository)
    repository.get_by_email.return_value = user
    return repository


def build_session_repository() -> Mock:
    return Mock(spec=AuthSessionRepository)


def test_login_user_returns_access_and_refresh_tokens(
    auth_settings: Settings,
) -> None:
    user = build_user()
    user_repository = build_user_repository(user)
    session_repository = build_session_repository()
    request = LoginRequest(
        email="Rahul@Gmail.com",
        password="familykart123",
    )

    response = login_user(
        request,
        user_repository,
        session_repository,
        config=auth_settings,
    )

    user_repository.get_by_email.assert_called_once_with("rahul@gmail.com")
    assert response.token_type == "bearer"
    assert response.access_token_expires_in == 900
    assert response.refresh_token_expires_in == 2_592_000
    assert (
        decode_token(
            response.access_token,
            expected_type=TokenType.ACCESS,
            config=auth_settings,
        ).subject
        == user.id
    )
    session_repository.create.assert_called_once_with(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(response.refresh_token),
        expires_at=decode_token(
            response.refresh_token,
            expected_type=TokenType.REFRESH,
            config=auth_settings,
        ).expires_at,
    )
    assert (
        decode_token(
            response.refresh_token,
            expected_type=TokenType.REFRESH,
            config=auth_settings,
        ).subject
        == user.id
    )


def test_login_user_rejects_incorrect_password(
    auth_settings: Settings,
) -> None:
    user_repository = build_user_repository(build_user())
    session_repository = build_session_repository()
    request = LoginRequest(
        email="rahul@gmail.com",
        password="incorrect-password",
    )

    with pytest.raises(InvalidCredentialsError):
        login_user(
            request,
            user_repository,
            session_repository,
            config=auth_settings,
        )

    session_repository.create.assert_not_called()


def test_login_user_rejects_unknown_email(auth_settings: Settings) -> None:
    user_repository = build_user_repository(None)
    session_repository = build_session_repository()
    request = LoginRequest(
        email="unknown@gmail.com",
        password="familykart123",
    )

    with pytest.raises(InvalidCredentialsError):
        login_user(
            request,
            user_repository,
            session_repository,
            config=auth_settings,
        )

    session_repository.create.assert_not_called()


def test_login_user_rejects_inactive_account(auth_settings: Settings) -> None:
    user_repository = build_user_repository(build_user(is_active=False))
    session_repository = build_session_repository()
    request = LoginRequest(
        email="rahul@gmail.com",
        password="familykart123",
    )

    with pytest.raises(InvalidCredentialsError):
        login_user(
            request,
            user_repository,
            session_repository,
            config=auth_settings,
        )

    session_repository.create.assert_not_called()
