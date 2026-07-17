from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.households import HouseholdRepository
from app.schemas.households import CreateHouseholdRequest, HouseholdResponse
from app.services.households import create_household

router = APIRouter(prefix="/api/v1/households", tags=["households"])


@router.post("", response_model=HouseholdResponse, status_code=status.HTTP_201_CREATED)
def create_user_household(
    data: CreateHouseholdRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> HouseholdResponse:
    household = create_household(data, current_user, HouseholdRepository(db))
    return HouseholdResponse.model_validate(household)
