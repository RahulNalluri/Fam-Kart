from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import ShoppingSessionRepository
from app.schemas.shopping_sessions import ShoppingSessionResponse
from app.services.shopping_sessions import (
    ActiveShoppingSessionExistsError,
    ShoppingSessionHouseholdNotFoundError,
    ShoppingSessionNotFoundError,
    complete_shopping_session,
    create_shopping_session,
    get_shopping_session,
    list_shopping_sessions,
)

router = APIRouter(
    prefix="/api/v1/households/{household_id}/shopping-sessions",
    tags=["shopping sessions"],
)


@router.post(
    "",
    response_model=ShoppingSessionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_current_household_shopping_session(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ShoppingSessionResponse:
    try:
        shopping_session = create_shopping_session(
            household_id,
            current_user,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except ShoppingSessionHouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error
    except ActiveShoppingSessionExistsError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An active shopping session already exists.",
        ) from error

    return ShoppingSessionResponse.model_validate(shopping_session)


@router.get("", response_model=list[ShoppingSessionResponse])
def list_current_household_shopping_sessions(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[ShoppingSessionResponse]:
    try:
        shopping_sessions = list_shopping_sessions(
            household_id,
            current_user,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except ShoppingSessionHouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error

    return [
        ShoppingSessionResponse.model_validate(shopping_session)
        for shopping_session in shopping_sessions
    ]


@router.get("/{session_id}", response_model=ShoppingSessionResponse)
def read_current_household_shopping_session(
    household_id: UUID,
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ShoppingSessionResponse:
    try:
        shopping_session = get_shopping_session(
            household_id,
            session_id,
            current_user,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except ShoppingSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopping session not found.",
        ) from error

    return ShoppingSessionResponse.model_validate(shopping_session)


@router.patch(
    "/{session_id}/complete",
    response_model=ShoppingSessionResponse,
)
def complete_current_household_shopping_session(
    household_id: UUID,
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> ShoppingSessionResponse:
    try:
        shopping_session = complete_shopping_session(
            household_id,
            session_id,
            current_user,
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except ShoppingSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shopping session not found.",
        ) from error

    return ShoppingSessionResponse.model_validate(shopping_session)
