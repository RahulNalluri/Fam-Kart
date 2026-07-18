from app.models.household import Household
from app.models.user import User
from app.repositories.households import HouseholdRepository
from app.schemas.households import (
    CreateHouseholdRequest,
    HouseholdListItem,
)


def create_household(
    data: CreateHouseholdRequest,
    owner: User,
    repository: HouseholdRepository,
) -> Household:
    return repository.create_with_owner(name=data.name, owner_id=owner.id)


def list_user_households(
    user: User,
    repository: HouseholdRepository,
) -> list[HouseholdListItem]:
    return [
        HouseholdListItem(
            id=record.household.id,
            name=record.household.name,
            created_at=record.household.created_at,
            updated_at=record.household.updated_at,
            role=record.role,
            joined_at=record.joined_at,
        )
        for record in repository.list_for_user(user.id)
    ]
