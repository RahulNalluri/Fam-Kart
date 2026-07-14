from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.security import (
    InvalidTokenError,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


@pytest.fixture
def auth_settings() -> Settings:
    return Settings(
        environment="testing",
        jwt_secret_key="testing-jwt-secret-key-that-is-long-enough",
        access_token_expire_minutes=15,
        refresh_token_expire_days=30,
    )


def test_password_is_hashed_and_verified() -> None:
    password = "FamilyKart-Password-123"

    hashed_password = hash_password(password)

    assert hashed_password != password
    assert hashed_password.startswith("$argon2")
    assert verify_password(password, hashed_password) is True
    assert verify_password("wrong-password", hashed_password) is False


def test_password_hashes_use_unique_salts() -> None:
    password = "FamilyKart-Password-123"

    first_hash = hash_password(password)
    second_hash = hash_password(password)

    assert first_hash != second_hash
    assert verify_password(password, first_hash) is True
    assert verify_password(password, second_hash) is True


def test_malformed_password_hash_is_rejected() -> None:
    assert (
        verify_password(
            "FamilyKart-Password-123",
            "not-a-valid-password-hash",
        )
        is False
    )


def test_access_token_contains_expected_claims(
    auth_settings: Settings,
) -> None:
    user_id = uuid4()
    issued_at = datetime.now(UTC).replace(microsecond=0)

    token = create_access_token(
        user_id,
        config=auth_settings,
        now=issued_at,
    )
    payload = decode_token(
        token,
        expected_type=TokenType.ACCESS,
        config=auth_settings,
    )

    assert payload.subject == user_id
    assert payload.token_type == TokenType.ACCESS
    assert payload.issued_at == issued_at
    assert payload.expires_at == issued_at + timedelta(minutes=15)
    assert payload.issuer == auth_settings.jwt_issuer
    assert payload.audience == auth_settings.jwt_audience


def test_refresh_token_uses_refresh_expiration(
    auth_settings: Settings,
) -> None:
    user_id = uuid4()
    issued_at = datetime.now(UTC).replace(microsecond=0)

    token = create_refresh_token(
        user_id,
        config=auth_settings,
        now=issued_at,
    )
    payload = decode_token(
        token,
        expected_type=TokenType.REFRESH,
        config=auth_settings,
    )

    assert payload.subject == user_id
    assert payload.token_type == TokenType.REFRESH
    assert payload.expires_at == issued_at + timedelta(days=30)


def test_refresh_token_cannot_be_used_as_access_token(
    auth_settings: Settings,
) -> None:
    token = create_refresh_token(
        uuid4(),
        config=auth_settings,
    )

    with pytest.raises(
        InvalidTokenError,
        match="token type is invalid",
    ):
        decode_token(
            token,
            expected_type=TokenType.ACCESS,
            config=auth_settings,
        )


def test_tampered_token_is_rejected(auth_settings: Settings) -> None:
    token = create_access_token(
        uuid4(),
        config=auth_settings,
    )
    header, payload, signature = token.split(".")
    replacement = "A" if signature[0] != "A" else "B"
    tampered_signature = replacement + signature[1:]
    tampered_token = f"{header}.{payload}.{tampered_signature}"

    with pytest.raises(
        InvalidTokenError,
        match="invalid or expired",
    ):
        decode_token(
            tampered_token,
            expected_type=TokenType.ACCESS,
            config=auth_settings,
        )


def test_expired_token_is_rejected(auth_settings: Settings) -> None:
    expired_issued_at = datetime.now(UTC) - timedelta(minutes=16)
    token = create_access_token(
        uuid4(),
        config=auth_settings,
        now=expired_issued_at,
    )

    with pytest.raises(
        InvalidTokenError,
        match="invalid or expired",
    ):
        decode_token(
            token,
            expected_type=TokenType.ACCESS,
            config=auth_settings,
        )


def test_naive_token_datetime_is_rejected(
    auth_settings: Settings,
) -> None:
    naive_datetime = datetime.now().replace(microsecond=0)

    with pytest.raises(
        ValueError,
        match="timezone-aware datetime",
    ):
        create_access_token(
            uuid4(),
            config=auth_settings,
            now=naive_datetime,
        )


def test_jwt_secret_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("JWT_SECRET_KEY", raising=False)

    with pytest.raises(
        ValidationError,
        match="jwt_secret_key",
    ):
        Settings(_env_file=None)


def test_custom_secret_is_allowed_in_production() -> None:
    production_settings = Settings(
        environment="production",
        jwt_secret_key="production-secret-key-that-is-at-least-32-characters",
    )

    assert production_settings.environment == "production"
