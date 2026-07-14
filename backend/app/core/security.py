from datetime import UTC, datetime, timedelta
from enum import StrEnum
from uuid import UUID, uuid4

import jwt
from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.config import Settings, settings

password_hash = PasswordHash.recommended()
UNUSABLE_PASSWORD_HASH = "!"


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


class InvalidTokenError(ValueError):
    pass


class TokenPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    subject: UUID = Field(alias="sub")
    token_type: TokenType
    issued_at: datetime = Field(alias="iat")
    expires_at: datetime = Field(alias="exp")
    issuer: str = Field(alias="iss")
    audience: str = Field(alias="aud")
    token_id: UUID = Field(alias="jti")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return password_hash.verify(password, hashed_password)
    except UnknownHashError:
        return False


def create_access_token(
    subject: UUID,
    *,
    config: Settings = settings,
    now: datetime | None = None,
) -> str:
    return _create_token(
        subject=subject,
        token_type=TokenType.ACCESS,
        expires_delta=timedelta(
            minutes=config.access_token_expire_minutes,
        ),
        config=config,
        now=now,
    )


def create_refresh_token(
    subject: UUID,
    *,
    config: Settings = settings,
    now: datetime | None = None,
) -> str:
    return _create_token(
        subject=subject,
        token_type=TokenType.REFRESH,
        expires_delta=timedelta(
            days=config.refresh_token_expire_days,
        ),
        config=config,
        now=now,
    )


def decode_token(
    token: str,
    *,
    expected_type: TokenType,
    config: Settings = settings,
) -> TokenPayload:
    try:
        raw_payload = jwt.decode(
            token,
            key=config.jwt_secret_key.get_secret_value(),
            algorithms=[config.jwt_algorithm],
            audience=config.jwt_audience,
            issuer=config.jwt_issuer,
            options={
                "require": [
                    "sub",
                    "token_type",
                    "iat",
                    "exp",
                    "iss",
                    "aud",
                    "jti",
                ],
            },
        )
        payload = TokenPayload.model_validate(raw_payload)
    except (jwt.PyJWTError, ValidationError) as error:
        raise InvalidTokenError(
            "The authentication token is invalid or expired."
        ) from error

    if payload.token_type != expected_type:
        raise InvalidTokenError("The authentication token type is invalid.")

    return payload


def _create_token(
    *,
    subject: UUID,
    token_type: TokenType,
    expires_delta: timedelta,
    config: Settings,
    now: datetime | None,
) -> str:
    issued_at = now or datetime.now(UTC)

    if issued_at.tzinfo is None:
        raise ValueError("Token creation requires a timezone-aware datetime.")

    payload = {
        "sub": str(subject),
        "token_type": token_type.value,
        "iat": issued_at,
        "exp": issued_at + expires_delta,
        "iss": config.jwt_issuer,
        "aud": config.jwt_audience,
        "jti": str(uuid4()),
    }

    return jwt.encode(
        payload,
        key=config.jwt_secret_key.get_secret_value(),
        algorithm=config.jwt_algorithm,
    )
