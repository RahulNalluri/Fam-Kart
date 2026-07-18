from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
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
    HouseholdResponse,
)
from app.services.households import (
    HouseholdNotFoundError,
    HouseholdOwnerRequiredError,
    create_household,
    create_household_invitation,
    list_user_households,
)

router = APIRouter(prefix="/api/v1/households", tags=["households"])


@router.get("", response_model=list[HouseholdListItem])
def list_current_user_households(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> list[HouseholdListItem]:
    return list_user_households(current_user, HouseholdRepository(db))


@router.post("", response_model=HouseholdResponse, status_code=status.HTTP_201_CREATED)
def create_user_household(
    data: CreateHouseholdRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdResponse:
    household = create_household(data, current_user, HouseholdRepository(db))
    return HouseholdResponse.model_validate(household)


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
