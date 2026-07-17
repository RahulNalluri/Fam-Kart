from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.users import UserRepository
from app.schemas.auth import UserResponse
from app.schemas.users import DeleteUserAccountRequest, UpdateUserProfileRequest
from app.services.users import (
    HouseholdOwnershipError,
    IncorrectPasswordError,
    delete_user_account,
    update_user_profile,
)

router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("/me", response_model=UserResponse)
def read_current_user(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.patch("/me", response_model=UserResponse)
def update_current_user(
    data: UpdateUserProfileRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> UserResponse:
    user = update_user_profile(current_user, data, UserRepository(db))
    return UserResponse.model_validate(user)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_user(
    data: DeleteUserAccountRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        delete_user_account(
            current_user,
            data,
            UserRepository(db),
            HouseholdMemberRepository(db),
        )
    except IncorrectPasswordError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password confirmation is incorrect.",
        ) from error
    except HouseholdOwnershipError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transfer household ownership before deleting your account.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
