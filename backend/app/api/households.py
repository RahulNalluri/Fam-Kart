from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.household_invitations import HouseholdInvitationRepository
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.households import HouseholdRepository
from app.schemas.households import (
    CreateHouseholdRequest,
    HouseholdInvitationResponse,
    HouseholdListItem,
    HouseholdMemberResponse,
    HouseholdResponse,
    JoinHouseholdRequest,
    TransferHouseholdOwnershipRequest,
)
from app.services.households import (
    AlreadyHouseholdMemberError,
    HouseholdMemberNotFoundError,
    HouseholdNotFoundError,
    HouseholdOwnerCannotLeaveError,
    HouseholdOwnerRequiredError,
    HouseholdOwnershipTransferConflictError,
    InvalidHouseholdInvitationError,
    create_household,
    create_household_invitation,
    get_user_household,
    join_household,
    leave_household,
    list_household_members,
    list_user_households,
    transfer_household_ownership,
)

router = APIRouter(prefix="/api/v1/households", tags=["households"])


@router.get("", response_model=list[HouseholdListItem])
def list_current_user_households(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[HouseholdListItem]:
    return list_user_households(current_user, HouseholdRepository(db))


@router.get("/{household_id}", response_model=HouseholdListItem)
def read_user_household(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdListItem:
    try:
        return get_user_household(
            household_id,
            current_user,
            HouseholdRepository(db),
        )
    except HouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error


@router.get(
    "/{household_id}/members",
    response_model=list[HouseholdMemberResponse],
)
def list_current_household_members(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[HouseholdMemberResponse]:
    try:
        return list_household_members(
            household_id,
            current_user,
            HouseholdMemberRepository(db),
        )
    except HouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error


@router.delete(
    "/{household_id}/members/me",
    status_code=status.HTTP_204_NO_CONTENT,
)
def leave_current_household(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        leave_household(
            household_id,
            current_user,
            HouseholdMemberRepository(db),
        )
    except HouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error
    except HouseholdOwnerCannotLeaveError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transfer household ownership before leaving the household.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.patch(
    "/{household_id}/owner",
    status_code=status.HTTP_204_NO_CONTENT,
)
def transfer_current_household_ownership(
    household_id: UUID,
    data: TransferHouseholdOwnershipRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    try:
        transfer_household_ownership(
            household_id,
            data,
            current_user,
            HouseholdMemberRepository(db),
        )
    except HouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error
    except HouseholdOwnerRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only household owners can transfer ownership.",
        ) from error
    except HouseholdMemberNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household member not found.",
        ) from error
    except HouseholdOwnershipTransferConflictError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Choose another household member as the new owner.",
        ) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("", response_model=HouseholdResponse, status_code=status.HTTP_201_CREATED)
def create_user_household(
    data: CreateHouseholdRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdResponse:
    household = create_household(data, current_user, HouseholdRepository(db))
    return HouseholdResponse.model_validate(household)


@router.post(
    "/join",
    response_model=HouseholdListItem,
    status_code=status.HTTP_201_CREATED,
)
def join_user_household(
    data: JoinHouseholdRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdListItem:
    try:
        return join_household(
            data,
            current_user,
            HouseholdMemberRepository(db),
            HouseholdInvitationRepository(db),
        )
    except InvalidHouseholdInvitationError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation code is invalid or unavailable.",
        ) from error
    except AlreadyHouseholdMemberError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="You are already a member of this household.",
        ) from error


@router.post(
    "/{household_id}/invitations",
    response_model=HouseholdInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user_household_invitation(
    household_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdInvitationResponse:
    try:
        return create_household_invitation(
            household_id,
            current_user,
            HouseholdMemberRepository(db),
            HouseholdInvitationRepository(db),
        )
    except HouseholdNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Household not found.",
        ) from error
    except HouseholdOwnerRequiredError as error:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only household owners can create invitations.",
        ) from error
