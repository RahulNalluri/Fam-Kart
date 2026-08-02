from uuid import UUID

from app.core.grocery_dictionary import (
    CANONICAL_GROCERY_KEYS,
    normalize_canonical_grocery_key,
    normalize_grocery_alias,
    standard_grocery_alias_owner,
)
from app.models.household_grocery_alias import HouseholdGroceryAlias
from app.models.user import User
from app.repositories.household_grocery_aliases import (
    DuplicateHouseholdGroceryAliasError,
    HouseholdGroceryAliasRepository,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.schemas.household_grocery_aliases import (
    CreateHouseholdGroceryAliasRequest,
    UpdateHouseholdGroceryAliasRequest,
)


class HouseholdAliasHouseholdNotFoundError(ValueError):
    pass


class HouseholdGroceryAliasNotFoundError(ValueError):
    pass


class HouseholdGroceryAliasDuplicateError(ValueError):
    pass


class HouseholdGroceryAliasCanonicalKeyError(ValueError):
    pass


class HouseholdGroceryAliasStandardTermConflictError(ValueError):
    pass


def _require_membership_for_mutation(
    household_id: UUID,
    user: User,
    repository: HouseholdMemberRepository,
) -> None:
    memberships = repository.lock_for_users(
        household_id=household_id,
        user_ids={user.id},
    )
    if user.id not in memberships:
        raise HouseholdAliasHouseholdNotFoundError


def _validate_alias_mapping(alias: str, canonical_key: str) -> tuple[str, str]:
    normalized_alias = normalize_grocery_alias(alias)
    normalized_key = normalize_canonical_grocery_key(canonical_key)
    if normalized_key not in CANONICAL_GROCERY_KEYS:
        raise HouseholdGroceryAliasCanonicalKeyError

    standard_owner = standard_grocery_alias_owner(normalized_alias)
    if standard_owner is not None and standard_owner != normalized_key:
        raise HouseholdGroceryAliasStandardTermConflictError
    return normalized_alias, normalized_key


def create_household_grocery_alias(
    household_id: UUID,
    data: CreateHouseholdGroceryAliasRequest,
    user: User,
    alias_repository: HouseholdGroceryAliasRepository,
    member_repository: HouseholdMemberRepository,
) -> HouseholdGroceryAlias:
    _require_membership_for_mutation(household_id, user, member_repository)
    normalized_alias, canonical_key = _validate_alias_mapping(
        data.alias,
        data.canonical_key,
    )
    if alias_repository.normalized_alias_exists(
        household_id=household_id,
        normalized_alias=normalized_alias,
    ):
        raise HouseholdGroceryAliasDuplicateError

    try:
        return alias_repository.create(
            household_id=household_id,
            alias=data.alias,
            normalized_alias=normalized_alias,
            canonical_key=canonical_key,
            created_by_user_id=user.id,
        )
    except DuplicateHouseholdGroceryAliasError as error:
        raise HouseholdGroceryAliasDuplicateError from error


def list_household_grocery_aliases(
    household_id: UUID,
    user: User,
    alias_repository: HouseholdGroceryAliasRepository,
    member_repository: HouseholdMemberRepository,
) -> list[HouseholdGroceryAlias]:
    membership = member_repository.get_for_user_and_household(
        household_id=household_id,
        user_id=user.id,
    )
    if membership is None:
        raise HouseholdAliasHouseholdNotFoundError
    return alias_repository.list_for_household(household_id)


def update_household_grocery_alias(
    household_id: UUID,
    alias_id: UUID,
    data: UpdateHouseholdGroceryAliasRequest,
    user: User,
    alias_repository: HouseholdGroceryAliasRepository,
    member_repository: HouseholdMemberRepository,
) -> HouseholdGroceryAlias:
    _require_membership_for_mutation(household_id, user, member_repository)
    grocery_alias = alias_repository.get_for_household(
        alias_id=alias_id,
        household_id=household_id,
    )
    if grocery_alias is None:
        raise HouseholdGroceryAliasNotFoundError

    alias = data.alias if data.alias is not None else grocery_alias.alias
    canonical_key = (
        data.canonical_key
        if data.canonical_key is not None
        else grocery_alias.canonical_key
    )
    normalized_alias, normalized_key = _validate_alias_mapping(
        alias,
        canonical_key,
    )
    if alias_repository.normalized_alias_exists(
        household_id=household_id,
        normalized_alias=normalized_alias,
        excluding_alias_id=grocery_alias.id,
    ):
        raise HouseholdGroceryAliasDuplicateError

    grocery_alias.alias = alias
    grocery_alias.normalized_alias = normalized_alias
    grocery_alias.canonical_key = normalized_key
    try:
        return alias_repository.update(grocery_alias)
    except DuplicateHouseholdGroceryAliasError as error:
        raise HouseholdGroceryAliasDuplicateError from error


def delete_household_grocery_alias(
    household_id: UUID,
    alias_id: UUID,
    user: User,
    alias_repository: HouseholdGroceryAliasRepository,
    member_repository: HouseholdMemberRepository,
) -> None:
    _require_membership_for_mutation(household_id, user, member_repository)
    grocery_alias = alias_repository.get_for_household(
        alias_id=alias_id,
        household_id=household_id,
    )
    if grocery_alias is None:
        raise HouseholdGroceryAliasNotFoundError
    alias_repository.delete(grocery_alias)
