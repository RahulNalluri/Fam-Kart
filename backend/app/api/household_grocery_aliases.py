from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.household_grocery_aliases import (
    HouseholdGroceryAliasRepository,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.schemas.household_grocery_aliases import (
    CreateHouseholdGroceryAliasRequest,
    HouseholdGroceryAliasResponse,
    UpdateHouseholdGroceryAliasRequest,
)
from app.services.household_grocery_aliases import (
    HouseholdAliasHouseholdNotFoundError,
    HouseholdGroceryAliasCanonicalKeyError,
    HouseholdGroceryAliasDuplicateError,
    HouseholdGroceryAliasNotFoundError,
    HouseholdGroceryAliasStandardTermConflictError,
    create_household_grocery_alias,
    delete_household_grocery_alias,
    list_household_grocery_aliases,
    update_household_grocery_alias,
)

router = APIRouter(
    prefix="/api/v1/households/{household_id}/grocery-aliases",
    tags=["household grocery aliases"],
)


def _raise_household_not_found(error: Exception) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Household not found.",
    ) from error


def _raise_alias_not_found(error: Exception) -> None:
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Household grocery alias not found.",
    ) from error


def _raise_alias_validation_error(error: Exception) -> None:
    if isinstance(error, HouseholdGroceryAliasCanonicalKeyError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Canonical grocery item is not supported.",
        ) from error
    if isinstance(error, HouseholdGroceryAliasStandardTermConflictError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="That standard grocery term belongs to another item.",
        ) from error
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="This household already uses that grocery alias.",
    ) from error


@router.post(
    "",
    response_model=HouseholdGroceryAliasResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_current_household_grocery_alias(
    household_id: UUID,
    data: CreateHouseholdGroceryAliasRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdGroceryAliasResponse:
    try:
        grocery_alias = create_household_grocery_alias(
            household_id,
            data,
            current_user,
            HouseholdGroceryAliasRepository(db),
            HouseholdMemberRepository(db),
        )
    except HouseholdAliasHouseholdNotFoundError as error:
        _raise_household_not_found(error)
    except (
        HouseholdGroceryAliasCanonicalKeyError,
        HouseholdGroceryAliasDuplicateError,
        HouseholdGroceryAliasStandardTermConflictError,
    ) as error:
        _raise_alias_validation_error(error)

    return HouseholdGroceryAliasResponse.model_validate(grocery_alias)


@router.get("", response_model=list[HouseholdGroceryAliasResponse])
def list_current_household_grocery_aliases(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[HouseholdGroceryAliasResponse]:
    try:
        grocery_aliases = list_household_grocery_aliases(
            household_id,
            current_user,
            HouseholdGroceryAliasRepository(db),
            HouseholdMemberRepository(db),
        )
    except HouseholdAliasHouseholdNotFoundError as error:
        _raise_household_not_found(error)

    return [
        HouseholdGroceryAliasResponse.model_validate(grocery_alias)
        for grocery_alias in grocery_aliases
    ]


@router.patch("/{alias_id}", response_model=HouseholdGroceryAliasResponse)
def update_current_household_grocery_alias(
    household_id: UUID,
    alias_id: UUID,
    data: UpdateHouseholdGroceryAliasRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdGroceryAliasResponse:
    try:
        grocery_alias = update_household_grocery_alias(
            household_id,
            alias_id,
            data,
            current_user,
            HouseholdGroceryAliasRepository(db),
            HouseholdMemberRepository(db),
        )
    except HouseholdAliasHouseholdNotFoundError as error:
        _raise_household_not_found(error)
    except HouseholdGroceryAliasNotFoundError as error:
        _raise_alias_not_found(error)
    except (
        HouseholdGroceryAliasCanonicalKeyError,
        HouseholdGroceryAliasDuplicateError,
        HouseholdGroceryAliasStandardTermConflictError,
    ) as error:
        _raise_alias_validation_error(error)

    return HouseholdGroceryAliasResponse.model_validate(grocery_alias)


@router.delete("/{alias_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_current_household_grocery_alias(
    household_id: UUID,
    alias_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        delete_household_grocery_alias(
            household_id,
            alias_id,
            current_user,
            HouseholdGroceryAliasRepository(db),
            HouseholdMemberRepository(db),
        )
    except HouseholdAliasHouseholdNotFoundError as error:
        _raise_household_not_found(error)
    except HouseholdGroceryAliasNotFoundError as error:
        _raise_alias_not_found(error)

    return Response(status_code=status.HTTP_204_NO_CONTENT)
