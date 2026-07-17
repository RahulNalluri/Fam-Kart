from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest

from app.core.config import Settings
from app.core.security import (
    TokenType,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_refresh_token,
)
from app.models.auth_session import AuthSession
from app.models.user import User
from app.repositories.auth_sessions import AuthSessionRepository
from app.repositories.users import UserRepository
from app.schemas.auth import RefreshTokenRequest
from app.services.auth import InvalidRefreshTokenError, refresh_tokens


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="testing",
        jwt_secret_key="testing-jwt-secret-key-that-is-long-enough",
        access_token_expire_minutes=15,
        refresh_token_expire_days=30,
    )


def test_refresh_tokens_rotates_the_stored_session(
    auth_settings: Settings,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    user = User(
        id=uuid4(),
        email="rahul@gmail.com",
        display_name="Rahul",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
        is_active=True,
    )
    old_token = create_refresh_token(user.id, config=auth_settings, now=now)
    old_payload = decode_token(
        old_token,
        expected_type=TokenType.REFRESH,
        config=auth_settings,
    )
    auth_session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(old_token),
        expires_at=old_payload.expires_at,
    )
    user_repository = Mock(spec=UserRepository)
    user_repository.get_by_id.return_value = user
    session_repository = Mock(spec=AuthSessionRepository)
    session_repository.get_by_refresh_token_hash.return_value = auth_session

    response = refresh_tokens(
        RefreshTokenRequest(refresh_token=old_token),
        user_repository,
        session_repository,
        config=auth_settings,
        now=now,
    )

    assert response.refresh_token != old_token
    assert (
        decode_token(
            response.access_token,
            expected_type=TokenType.ACCESS,
            config=auth_settings,
        ).subject
        == user.id
    )
    session_repository.rotate.assert_called_once()
    rotation = session_repository.rotate.call_args.kwargs
    assert rotation["new_refresh_token_hash"] == hash_refresh_token(
        response.refresh_token
    )
    assert rotation["rotated_at"] == now


@pytest.mark.parametrize("session_state", ["missing", "revoked", "expired"])
def test_refresh_tokens_rejects_inactive_sessions(
    auth_settings: Settings,
    session_state: str,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    user = User(
        id=uuid4(),
        email="rahul@gmail.com",
        display_name="Rahul",
        password_hash="!",
        preferred_language="en",
        is_active=True,
    )
    token = create_refresh_token(user.id, config=auth_settings, now=now)
    session = AuthSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(token),
        expires_at=(
            now - timedelta(seconds=1)
            if session_state == "expired"
            else now + timedelta(days=30)
        ),
        revoked_at=now if session_state == "revoked" else None,
    )
    user_repository = Mock(spec=UserRepository)
    session_repository = Mock(spec=AuthSessionRepository)
    session_repository.get_by_refresh_token_hash.return_value = (
        None if session_state == "missing" else session
    )

    with pytest.raises(InvalidRefreshTokenError):
        refresh_tokens(
            RefreshTokenRequest(refresh_token=token),
            user_repository,
            session_repository,
            config=auth_settings,
            now=now,
        )

    session_repository.rotate.assert_not_called()
