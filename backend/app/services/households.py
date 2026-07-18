from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import Settings, settings
from app.core.invitations import generate_invitation_code, hash_invitation_code
from app.models.household import Household
from app.models.household_member import HouseholdRole
from app.models.user import User
from app.repositories.household_invitations import HouseholdInvitationRepository
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.households import HouseholdRepository
from app.schemas.households import (
    CreateHouseholdRequest,
    HouseholdInvitationResponse,
    HouseholdListItem,
)


class HouseholdNotFoundError(ValueError):
    pass


class HouseholdOwnerRequiredError(ValueError):
    pass


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


def create_household_invitation(
    household_id: UUID,
    creator: User,
    member_repository: HouseholdMemberRepository,
    invitation_repository: HouseholdInvitationRepository,
    *,
    config: Settings = settings,
    now: datetime | None = None,
) -> HouseholdInvitationResponse:
    membership = member_repository.get_for_user_and_household(
        user_id=creator.id,
        household_id=household_id,
    )
    if membership is None:
        raise HouseholdNotFoundError
    if membership.role != HouseholdRole.OWNER:
        raise HouseholdOwnerRequiredError

    created_at = now or datetime.now(UTC)
    code = generate_invitation_code()
    invitation = invitation_repository.create(
        household_id=household_id,
        created_by_user_id=creator.id,
        code_hash=hash_invitation_code(code),
        expires_at=created_at
        + timedelta(hours=config.household_invitation_expire_hours),
    )
    return HouseholdInvitationResponse(
        id=invitation.id,
        household_id=invitation.household_id,
        code=code,
        expires_at=invitation.expires_at,
    )
