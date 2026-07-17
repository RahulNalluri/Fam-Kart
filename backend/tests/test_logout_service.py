from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.core.config import Settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_refresh_token,
)
from app.models.auth_session import AuthSession
from app.repositories.auth_sessions import AuthSessionRepository
from app.schemas.auth import LogoutRequest
from app.services.auth import InvalidLogoutTokenError, logout_user


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="testing",
        jwt_secret_key="testing-jwt-secret-key-that-is-long-enough",
        access_token_expire_minutes=15,
        refresh_token_expire_days=30,
    )


def build_session(
    token: str,
    *,
    config: Settings,
    revoked_at: datetime | None = None,
    expires_at: datetime | None = None,
    user_id: UUID | None = None,
) -> AuthSession:
    payload = decode_token(
        token,
        expected_type=TokenType.REFRESH,
        config=config,
    )
    return AuthSession(
        id=uuid4(),
        user_id=user_id or payload.subject,
        refresh_token_hash=hash_refresh_token(token),
        expires_at=expires_at or payload.expires_at,
        revoked_at=revoked_at,
    )


def test_logout_user_revokes_active_session(auth_settings: Settings) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    token = create_refresh_token(uuid4(), config=auth_settings, now=now)
    auth_session = build_session(token, config=auth_settings)
    repository = Mock(spec=AuthSessionRepository)
    repository.get_by_refresh_token_hash.return_value = auth_session

    result = logout_user(
        LogoutRequest(refresh_token=token),
        repository,
        config=auth_settings,
        now=now,
    )

    assert result is None
    repository.get_by_refresh_token_hash.assert_called_once_with(
        hash_refresh_token(token)
    )
    repository.revoke.assert_called_once_with(auth_session, revoked_at=now)


@pytest.mark.parametrize("session_state", ["missing", "revoked", "expired"])
def test_logout_user_rejects_inactive_session(
    auth_settings: Settings,
    session_state: str,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    token = create_refresh_token(uuid4(), config=auth_settings, now=now)
    auth_session = build_session(
        token,
        config=auth_settings,
        revoked_at=now if session_state == "revoked" else None,
        expires_at=(now - timedelta(seconds=1) if session_state == "expired" else None),
    )
    repository = Mock(spec=AuthSessionRepository)
    repository.get_by_refresh_token_hash.return_value = (
        None if session_state == "missing" else auth_session
    )

    with pytest.raises(InvalidLogoutTokenError):
        logout_user(
            LogoutRequest(refresh_token=token),
            repository,
            config=auth_settings,
            now=now,
        )

    repository.revoke.assert_not_called()


def test_logout_user_rejects_session_owned_by_another_user(
    auth_settings: Settings,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    token = create_refresh_token(uuid4(), config=auth_settings, now=now)
    repository = Mock(spec=AuthSessionRepository)
    repository.get_by_refresh_token_hash.return_value = build_session(
        token,
        config=auth_settings,
        user_id=uuid4(),
    )

    with pytest.raises(InvalidLogoutTokenError):
        logout_user(
            LogoutRequest(refresh_token=token),
            repository,
            config=auth_settings,
            now=now,
        )

    repository.revoke.assert_not_called()


@pytest.mark.parametrize("token_kind", ["malformed", "access"])
def test_logout_user_rejects_invalid_token_type(
    auth_settings: Settings,
    token_kind: str,
) -> None:
    token = (
        "not-a-jwt"
        if token_kind == "malformed"
        else create_access_token(uuid4(), config=auth_settings)
    )
    repository = Mock(spec=AuthSessionRepository)

    with pytest.raises(InvalidLogoutTokenError):
        logout_user(
            LogoutRequest(refresh_token=token),
            repository,
            config=auth_settings,
        )

    repository.get_by_refresh_token_hash.assert_not_called()
    repository.revoke.assert_not_called()
