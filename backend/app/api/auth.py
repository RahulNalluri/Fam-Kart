from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.auth_sessions import AuthSessionRepository
from app.repositories.users import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import (
    EmailAlreadyRegisteredError,
    InvalidCredentialsError,
    InvalidLogoutTokenError,
    InvalidRefreshTokenError,
    login_user,
    logout_user,
    refresh_tokens,
    register_user,
)

router = APIRouter(prefix="/api/v1/auth", tags=["authentication"])


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    data: LogoutRequest,
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        logout_user(data, AuthSessionRepository(db))
    except InvalidLogoutTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    data: RefreshTokenRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    try:
        return refresh_tokens(
            data,
            UserRepository(db),
            AuthSessionRepository(db),
        )
    except InvalidRefreshTokenError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


@router.post("/login", response_model=TokenResponse)
def login(
    data: LoginRequest,
    db: Annotated[Session, Depends(get_db)],
) -> TokenResponse:
    try:
        return login_user(
            data,
            UserRepository(db),
            AuthSessionRepository(db),
        )
    except InvalidCredentialsError as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(
    data: RegisterRequest,
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    try:
        user = register_user(data, UserRepository(db))
    except EmailAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists.",
        ) from error

    return UserResponse.model_validate(user)
