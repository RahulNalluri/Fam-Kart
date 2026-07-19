from datetime import UTC, datetime, timedelta
from uuid import UUID

from app.core.config import Settings, settings
from app.core.invitations import generate_invitation_code, hash_invitation_code
from app.models.household import Household
from app.models.household_member import HouseholdRole
from app.models.user import User
from app.repositories.household_invitations import (
    HouseholdInvitationNotActiveError,
    HouseholdInvitationRepository,
    HouseholdMembershipConflictError,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.households import HouseholdRepository
from app.schemas.households import (
    CreateHouseholdRequest,
    HouseholdInvitationResponse,
    HouseholdListItem,
    JoinHouseholdRequest,
)


class HouseholdNotFoundError(ValueError):
    pass


class HouseholdOwnerRequiredError(ValueError):
    pass


class InvalidHouseholdInvitationError(ValueError):
    pass


class AlreadyHouseholdMemberError(ValueError):
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


def join_household(
    data: JoinHouseholdRequest,
    user: User,
    member_repository: HouseholdMemberRepository,
    invitation_repository: HouseholdInvitationRepository,
    *,
    now: datetime | None = None,
) -> HouseholdListItem:
    joined_at = now or datetime.now(UTC)
    invitation = invitation_repository.get_active_by_code_hash(
        hash_invitation_code(data.invitation_code),
        now=joined_at,
    )
    if invitation is None:
        raise InvalidHouseholdInvitationError

    existing_membership = member_repository.get_for_user_and_household(
        user_id=user.id,
        household_id=invitation.household_id,
    )
    if existing_membership is not None:
        raise AlreadyHouseholdMemberError

    try:
        membership = invitation_repository.consume_and_add_member(
            invitation,
            user_id=user.id,
            used_at=joined_at,
        )
    except HouseholdInvitationNotActiveError as error:
        raise InvalidHouseholdInvitationError from error
    except HouseholdMembershipConflictError as error:
        raise AlreadyHouseholdMemberError from error

    household = invitation.household
    return HouseholdListItem(
        id=household.id,
        name=household.name,
        created_at=household.created_at,
        updated_at=household.updated_at,
        role=membership.role,
        joined_at=membership.joined_at,
    )
