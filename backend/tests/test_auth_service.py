from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.security import TokenType, decode_token, hash_password
from app.models.user import User
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


def build_repository(user: User | None) -> Mock:
    repository = Mock(spec=UserRepository)
    repository.get_by_email.return_value = user
    return repository


def test_login_user_returns_access_and_refresh_tokens(
    auth_settings: Settings,
) -> None:
    user = build_user()
    repository = build_repository(user)
    request = LoginRequest(
        email="Rahul@Gmail.com",
        password="familykart123",
    )

    response = login_user(request, repository, config=auth_settings)

    repository.get_by_email.assert_called_once_with("rahul@gmail.com")
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
    repository = build_repository(build_user())
    request = LoginRequest(
        email="rahul@gmail.com",
        password="incorrect-password",
    )

    with pytest.raises(InvalidCredentialsError):
        login_user(request, repository, config=auth_settings)


def test_login_user_rejects_unknown_email(auth_settings: Settings) -> None:
    repository = build_repository(None)
    request = LoginRequest(
        email="unknown@gmail.com",
        password="familykart123",
    )

    with pytest.raises(InvalidCredentialsError):
        login_user(request, repository, config=auth_settings)


def test_login_user_rejects_inactive_account(auth_settings: Settings) -> None:
    repository = build_repository(build_user(is_active=False))
    request = LoginRequest(
        email="rahul@gmail.com",
        password="familykart123",
    )

    with pytest.raises(InvalidCredentialsError):
        login_user(request, repository, config=auth_settings)
