import pytest
from pydantic import ValidationError

from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
)


def test_login_request_normalizes_email() -> None:
    request = LoginRequest(
        email="Rahul@Example.com",
        password="familykart123",
    )

    assert request.email == "rahul@example.com"
    assert request.password == "familykart123"


@pytest.mark.parametrize(
    ("email", "password"),
    [
        ("not-an-email", "familykart123"),
        ("rahul@example.com", ""),
        ("rahul@example.com", "x" * 129),
    ],
)
def test_login_request_rejects_invalid_credentials_shape(
    email: str,
    password: str,
) -> None:
    with pytest.raises(ValidationError):
        LoginRequest(email=email, password=password)


def test_token_response_contains_both_token_lifetimes() -> None:
    response = TokenResponse(
        access_token="access-token",
        refresh_token="refresh-token",
        access_token_expires_in=900,
        refresh_token_expires_in=2_592_000,
    )

    assert response.token_type == "bearer"
    assert response.access_token_expires_in == 900
    assert response.refresh_token_expires_in == 2_592_000


def test_refresh_token_request_requires_a_token() -> None:
    request = RefreshTokenRequest(refresh_token="refresh-token")

    assert request.refresh_token == "refresh-token"

    with pytest.raises(ValidationError):
        RefreshTokenRequest(refresh_token="")


def test_logout_request_requires_a_token() -> None:
    request = LogoutRequest(refresh_token="refresh-token")

    assert request.refresh_token == "refresh-token"

    with pytest.raises(ValidationError):
        LogoutRequest(refresh_token="")


@pytest.mark.parametrize(
    "field",
    ["access_token_expires_in", "refresh_token_expires_in"],
)
def test_token_response_rejects_non_positive_lifetimes(field: str) -> None:
    data = {
        "access_token": "access-token",
        "refresh_token": "refresh-token",
        "access_token_expires_in": 900,
        "refresh_token_expires_in": 2_592_000,
    }
    data[field] = 0

    with pytest.raises(ValidationError):
        TokenResponse.model_validate(data)
