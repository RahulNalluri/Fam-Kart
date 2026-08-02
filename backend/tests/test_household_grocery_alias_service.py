from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from app.models import HouseholdGroceryAlias, HouseholdMember, HouseholdRole, User
from app.repositories.household_grocery_aliases import (
    DuplicateHouseholdGroceryAliasError,
    HouseholdGroceryAliasRepository,
)
from app.repositories.household_members import HouseholdMemberRepository
from app.schemas.household_grocery_aliases import (
    CreateHouseholdGroceryAliasRequest,
    UpdateHouseholdGroceryAliasRequest,
)
from app.services.household_grocery_aliases import (
    HouseholdAliasHouseholdNotFoundError,
    HouseholdGroceryAliasCanonicalKeyError,
    HouseholdGroceryAliasDuplicateError,
    HouseholdGroceryAliasNotFoundError,
    HouseholdGroceryAliasStandardTermConflictError,
    create_household_grocery_alias,
    delete_household_grocery_alias,
    list_household_grocery_aliases,
    update_household_grocery_alias,
)


def build_user() -> User:
    return User(
        id=uuid4(),
        email="household-alias-service@example.com",
        display_name="Household Alias User",
        password_hash="!",
        preferred_language="en",
    )


def build_membership(
    user_id: UUID,
    household_id: UUID,
    role: HouseholdRole = HouseholdRole.MEMBER,
) -> HouseholdMember:
    return HouseholdMember(
        id=uuid4(),
        user_id=user_id,
        household_id=household_id,
        role=role,
    )


def build_alias(
    household_id: UUID,
    user_id: UUID,
    *,
    alias: str = "Morning milk",
    normalized_alias: str = "morning milk",
    canonical_key: str = "milk",
) -> HouseholdGroceryAlias:
    return HouseholdGroceryAlias(
        id=uuid4(),
        household_id=household_id,
        alias=alias,
        normalized_alias=normalized_alias,
        canonical_key=canonical_key,
        created_by_user_id=user_id,
    )


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_current_household_member_can_create_alias(role: HouseholdRole) -> None:
    user = build_user()
    household_id = uuid4()
    expected = build_alias(household_id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id, role),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)
    alias_repository.normalized_alias_exists.return_value = False
    alias_repository.create.return_value = expected

    result = create_household_grocery_alias(
        household_id,
        CreateHouseholdGroceryAliasRequest(
            alias="  Morning   Milk ",
            canonical_key="MILK",
        ),
        user,
        alias_repository,
        member_repository,
    )

    assert result is expected
    member_repository.lock_for_users.assert_called_once_with(
        household_id=household_id,
        user_ids={user.id},
    )
    alias_repository.create.assert_called_once_with(
        household_id=household_id,
        alias="Morning Milk",
        normalized_alias="morning milk",
        canonical_key="milk",
        created_by_user_id=user.id,
    )


def test_outsider_cannot_create_or_discover_household_aliases() -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {}
    member_repository.get_for_user_and_household.return_value = None
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)

    with pytest.raises(HouseholdAliasHouseholdNotFoundError):
        create_household_grocery_alias(
            household_id,
            CreateHouseholdGroceryAliasRequest(
                alias="Morning milk",
                canonical_key="milk",
            ),
            user,
            alias_repository,
            member_repository,
        )
    with pytest.raises(HouseholdAliasHouseholdNotFoundError):
        list_household_grocery_aliases(
            household_id,
            user,
            alias_repository,
            member_repository,
        )

    alias_repository.create.assert_not_called()
    alias_repository.list_for_household.assert_not_called()


def test_create_rejects_unknown_canonical_key() -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)

    with pytest.raises(HouseholdGroceryAliasCanonicalKeyError):
        create_household_grocery_alias(
            household_id,
            CreateHouseholdGroceryAliasRequest(
                alias="Cleaning liquid",
                canonical_key="dish_soap",
            ),
            user,
            alias_repository,
            member_repository,
        )

    alias_repository.create.assert_not_called()


@pytest.mark.parametrize("alias", ["milk", "పాలు", "Palu"])
def test_create_prevents_remapping_standard_terms(alias: str) -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)

    with pytest.raises(HouseholdGroceryAliasStandardTermConflictError):
        create_household_grocery_alias(
            household_id,
            CreateHouseholdGroceryAliasRequest(
                alias=alias,
                canonical_key="rice",
            ),
            user,
            alias_repository,
            member_repository,
        )

    alias_repository.create.assert_not_called()


@pytest.mark.parametrize("race", [False, True])
def test_create_translates_duplicate_alias_errors(race: bool) -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)
    alias_repository.normalized_alias_exists.return_value = not race
    if race:
        alias_repository.create.side_effect = DuplicateHouseholdGroceryAliasError

    with pytest.raises(HouseholdGroceryAliasDuplicateError):
        create_household_grocery_alias(
            household_id,
            CreateHouseholdGroceryAliasRequest(
                alias="Morning milk",
                canonical_key="milk",
            ),
            user,
            alias_repository,
            member_repository,
        )


def test_member_can_list_household_aliases() -> None:
    user = build_user()
    household_id = uuid4()
    expected = [build_alias(household_id, user.id)]
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.get_for_user_and_household.return_value = build_membership(
        user.id,
        household_id,
    )
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)
    alias_repository.list_for_household.return_value = expected

    assert (
        list_household_grocery_aliases(
            household_id,
            user,
            alias_repository,
            member_repository,
        )
        == expected
    )


def test_member_can_update_alias_and_canonical_key() -> None:
    user = build_user()
    household_id = uuid4()
    grocery_alias = build_alias(household_id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)
    alias_repository.get_for_household.return_value = grocery_alias
    alias_repository.normalized_alias_exists.return_value = False
    alias_repository.update.return_value = grocery_alias

    result = update_household_grocery_alias(
        household_id,
        grocery_alias.id,
        UpdateHouseholdGroceryAliasRequest(
            alias="  Weekly   rice ",
            canonical_key="RICE",
        ),
        user,
        alias_repository,
        member_repository,
    )

    assert result is grocery_alias
    assert grocery_alias.alias == "Weekly rice"
    assert grocery_alias.normalized_alias == "weekly rice"
    assert grocery_alias.canonical_key == "rice"
    alias_repository.normalized_alias_exists.assert_called_once_with(
        household_id=household_id,
        normalized_alias="weekly rice",
        excluding_alias_id=grocery_alias.id,
    )


def test_update_rejects_missing_or_duplicate_alias() -> None:
    user = build_user()
    household_id = uuid4()
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)
    alias_repository.get_for_household.return_value = None

    with pytest.raises(HouseholdGroceryAliasNotFoundError):
        update_household_grocery_alias(
            household_id,
            uuid4(),
            UpdateHouseholdGroceryAliasRequest(alias="Weekly rice"),
            user,
            alias_repository,
            member_repository,
        )

    grocery_alias = build_alias(household_id, user.id)
    alias_repository.get_for_household.return_value = grocery_alias
    alias_repository.normalized_alias_exists.return_value = True
    with pytest.raises(HouseholdGroceryAliasDuplicateError):
        update_household_grocery_alias(
            household_id,
            grocery_alias.id,
            UpdateHouseholdGroceryAliasRequest(alias="Existing alias"),
            user,
            alias_repository,
            member_repository,
        )
    alias_repository.update.assert_not_called()


def test_update_translates_repository_duplicate_race() -> None:
    user = build_user()
    household_id = uuid4()
    grocery_alias = build_alias(household_id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)
    alias_repository.get_for_household.return_value = grocery_alias
    alias_repository.normalized_alias_exists.return_value = False
    alias_repository.update.side_effect = DuplicateHouseholdGroceryAliasError

    with pytest.raises(HouseholdGroceryAliasDuplicateError):
        update_household_grocery_alias(
            household_id,
            grocery_alias.id,
            UpdateHouseholdGroceryAliasRequest(alias="Weekly rice"),
            user,
            alias_repository,
            member_repository,
        )


def test_member_can_delete_alias_and_missing_alias_is_rejected() -> None:
    user = build_user()
    household_id = uuid4()
    grocery_alias = build_alias(household_id, user.id)
    member_repository = Mock(spec=HouseholdMemberRepository)
    member_repository.lock_for_users.return_value = {
        user.id: build_membership(user.id, household_id),
    }
    alias_repository = Mock(spec=HouseholdGroceryAliasRepository)
    alias_repository.get_for_household.return_value = grocery_alias

    delete_household_grocery_alias(
        household_id,
        grocery_alias.id,
        user,
        alias_repository,
        member_repository,
    )
    alias_repository.delete.assert_called_once_with(grocery_alias)

    alias_repository.reset_mock()
    alias_repository.get_for_household.return_value = None
    with pytest.raises(HouseholdGroceryAliasNotFoundError):
        delete_household_grocery_alias(
            household_id,
            uuid4(),
            user,
            alias_repository,
            member_repository,
        )
    alias_repository.delete.assert_not_called()
