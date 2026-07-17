from app.models.household import Household
from app.models.user import User
from app.repositories.households import HouseholdRepository
from app.schemas.households import CreateHouseholdRequest


def create_household(
    data: CreateHouseholdRequest,
    owner: User,
    repository: HouseholdRepository,
) -> Household:
    return repository.create_with_owner(name=data.name, owner_id=owner.id)
