from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.grocery_items import GroceryItemRepository
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.shopping_sessions import ShoppingSessionRepository
from app.schemas.grocery_items import (
    CreateGroceryItemRequest,
    GroceryItemResponse,
    UpdateGroceryItemRequest,
)
from app.services.grocery_items import (
    GroceryItemAssigneeNotFoundError,
    GroceryItemCompletedError,
    GroceryItemNotFoundError,
    GroceryItemShoppingSessionCompletedError,
    GroceryItemShoppingSessionNotFoundError,
    create_grocery_item,
    list_grocery_items,
    update_grocery_item,
)

router = APIRouter(
    prefix=("/api/v1/households/{household_id}/shopping-sessions/{session_id}/items"),
    tags=["grocery items"],
)


@router.post(
    "",
    response_model=GroceryItemResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_current_session_grocery_item(
    household_id: UUID,
    session_id: UUID,
    data: CreateGroceryItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GroceryItemResponse:
    try:
        item = create_grocery_item(
            household_id,
            session_id,
            data,
            current_user,
            GroceryItemRepository(db),
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except GroceryItemShoppingSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This shopping session could not be found or you do not have "
                "access to it."
            ),
        ) from error
    except GroceryItemShoppingSessionCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot add items because this shopping session is already "
                "completed."
            ),
        ) from error
    except GroceryItemAssigneeNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected person is not a member of this household.",
        ) from error

    return GroceryItemResponse.model_validate(item)


@router.get("", response_model=list[GroceryItemResponse])
def list_current_session_grocery_items(
    household_id: UUID,
    session_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[GroceryItemResponse]:
    try:
        items = list_grocery_items(
            household_id,
            session_id,
            current_user,
            GroceryItemRepository(db),
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except GroceryItemShoppingSessionNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This shopping session could not be found or you do not have "
                "access to it."
            ),
        ) from error

    return [GroceryItemResponse.model_validate(item) for item in items]


@router.patch("/{item_id}", response_model=GroceryItemResponse)
def update_current_session_grocery_item(
    household_id: UUID,
    session_id: UUID,
    item_id: UUID,
    data: UpdateGroceryItemRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> GroceryItemResponse:
    try:
        item = update_grocery_item(
            household_id,
            session_id,
            item_id,
            data,
            current_user,
            GroceryItemRepository(db),
            ShoppingSessionRepository(db),
            HouseholdMemberRepository(db),
        )
    except GroceryItemNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                "This grocery item could not be found or you do not have access "
                "to it."
            ),
        ) from error
    except GroceryItemShoppingSessionCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "You cannot edit items because this shopping session is already "
                "completed."
            ),
        ) from error
    except GroceryItemCompletedError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reopen this grocery item before editing it.",
        ) from error
    except GroceryItemAssigneeNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The selected person is not a member of this household.",
        ) from error

    return GroceryItemResponse.model_validate(item)
