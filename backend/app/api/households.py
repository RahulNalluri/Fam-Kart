from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.households import HouseholdRepository
from app.schemas.households import (
    CreateHouseholdRequest,
    HouseholdListItem,
    HouseholdResponse,
)
from app.services.households import create_household, list_user_households

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
