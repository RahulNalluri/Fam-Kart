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
from app.repositories.households import HouseholdMembershipRecord, HouseholdRepository
from app.schemas.households import (
    CreateHouseholdRequest,
    HouseholdInvitationResponse,
    HouseholdListItem,
    HouseholdMemberResponse,
    JoinHouseholdRequest,
    TransferHouseholdOwnershipRequest,
    UpdateHouseholdRequest,
)


class HouseholdNotFoundError(ValueError):
    pass


class HouseholdOwnerRequiredError(ValueError):
    pass


class InvalidHouseholdInvitationError(ValueError):
    pass


class AlreadyHouseholdMemberError(ValueError):
    pass


class HouseholdOwnerCannotLeaveError(ValueError):
    pass


class HouseholdMemberNotFoundError(ValueError):
    pass


class HouseholdOwnershipTransferConflictError(ValueError):
    pass


class HouseholdOwnerCannotBeRemovedError(ValueError):
    pass


def _household_membership_response(
    record: HouseholdMembershipRecord,
) -> HouseholdListItem:
    return HouseholdListItem(
        id=record.household.id,
        name=record.household.name,
        created_at=record.household.created_at,
        updated_at=record.household.updated_at,
        role=record.role,
        joined_at=record.joined_at,
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
        _household_membership_response(record)
        for record in repository.list_for_user(user.id)
    ]


def get_user_household(
    household_id: UUID,
    user: User,
    repository: HouseholdRepository,
) -> HouseholdListItem:
    record = repository.get_for_user(
        household_id=household_id,
        user_id=user.id,
    )
    if record is None:
        raise HouseholdNotFoundError
    return _household_membership_response(record)


def update_household(
    household_id: UUID,
    data: UpdateHouseholdRequest,
    user: User,
    household_repository: HouseholdRepository,
    member_repository: HouseholdMemberRepository,
) -> Household:
    memberships = member_repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id},
    )
    membership = memberships.get(user.id)
    if membership is None:
        raise HouseholdNotFoundError
    if membership.role != HouseholdRole.OWNER:
        raise HouseholdOwnerRequiredError

    household = household_repository.get_by_id(household_id)
    if household is None:
        raise HouseholdNotFoundError
    household.name = data.name
    return household_repository.update(household)


def list_household_members(
    household_id: UUID,
    user: User,
    repository: HouseholdMemberRepository,
) -> list[HouseholdMemberResponse]:
    membership = repository.get_for_user_and_household(
        household_id=household_id,
        user_id=user.id,
    )
    if membership is None:
        raise HouseholdNotFoundError

    return [
        HouseholdMemberResponse(
            user_id=record.user_id,
            display_name=record.display_name,
            preferred_language=record.preferred_language,
            role=record.role,
            joined_at=record.joined_at,
        )
        for record in repository.list_for_household(household_id)
    ]


def leave_household(
    household_id: UUID,
    user: User,
    repository: HouseholdMemberRepository,
) -> None:
    membership = repository.get_for_user_and_household(
        household_id=household_id,
        user_id=user.id,
    )
    if membership is None:
        raise HouseholdNotFoundError
    if membership.role == HouseholdRole.OWNER:
        raise HouseholdOwnerCannotLeaveError

    repository.delete(membership)


def transfer_household_ownership(
    household_id: UUID,
    data: TransferHouseholdOwnershipRequest,
    user: User,
    repository: HouseholdMemberRepository,
) -> None:
    memberships = repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id, data.new_owner_user_id},
    )
    current_owner = memberships.get(user.id)
    new_owner = memberships.get(data.new_owner_user_id)
    if current_owner is None:
        raise HouseholdNotFoundError
    if current_owner.role != HouseholdRole.OWNER:
        raise HouseholdOwnerRequiredError
    if data.new_owner_user_id == user.id:
        raise HouseholdOwnershipTransferConflictError
    if new_owner is None:
        raise HouseholdMemberNotFoundError
    if new_owner.role != HouseholdRole.MEMBER:
        raise HouseholdOwnershipTransferConflictError

    repository.transfer_ownership(
        current_owner=current_owner,
        new_owner=new_owner,
    )


def remove_household_member(
    household_id: UUID,
    member_user_id: UUID,
    user: User,
    repository: HouseholdMemberRepository,
) -> None:
    memberships = repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id, member_user_id},
    )
    owner_membership = memberships.get(user.id)
    member_to_remove = memberships.get(member_user_id)
    if owner_membership is None:
        raise HouseholdNotFoundError
    if owner_membership.role != HouseholdRole.OWNER:
        raise HouseholdOwnerRequiredError
    if member_to_remove is None:
        raise HouseholdMemberNotFoundError
    if member_to_remove.role == HouseholdRole.OWNER:
        raise HouseholdOwnerCannotBeRemovedError

    repository.delete(member_to_remove)


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
