from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Household, HouseholdGroceryAlias, User
from app.repositories.household_grocery_aliases import (
    DuplicateHouseholdGroceryAliasError,
    HouseholdGroceryAliasRepository,
)


def create_test_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_dependencies(db: Session, *, suffix: str) -> tuple[User, Household]:
    user = User(
        id=uuid4(),
        email=f"alias-{suffix}@example.com",
        display_name="Alias Repository User",
        password_hash="!",
        preferred_language="en",
    )
    household = Household(name=f"Alias {suffix} Family")
    db.add_all([user, household])
    db.commit()
    return user, household


def test_repository_creates_gets_and_lists_household_aliases() -> None:
    db = create_test_session()
    try:
        user, household = create_dependencies(db, suffix="list")
        repository = HouseholdGroceryAliasRepository(db)
        second = repository.create(
            household_id=household.id,
            alias="Weekly rice",
            normalized_alias="weekly rice",
            canonical_key="rice",
            created_by_user_id=user.id,
        )
        first = repository.create(
            household_id=household.id,
            alias="Morning milk",
            normalized_alias="morning milk",
            canonical_key="milk",
            created_by_user_id=user.id,
        )

        assert (
            repository.get_for_household(
                alias_id=first.id,
                household_id=household.id,
            )
            is first
        )
        assert repository.list_for_household(household.id) == [first, second]
    finally:
        db.close()


def test_repository_scopes_aliases_to_household() -> None:
    db = create_test_session()
    try:
        user, household = create_dependencies(db, suffix="scope")
        other_household = Household(name="Other Alias Family")
        db.add(other_household)
        db.commit()
        repository = HouseholdGroceryAliasRepository(db)
        grocery_alias = repository.create(
            household_id=household.id,
            alias="Morning milk",
            normalized_alias="morning milk",
            canonical_key="milk",
            created_by_user_id=user.id,
        )

        assert (
            repository.get_for_household(
                alias_id=grocery_alias.id,
                household_id=other_household.id,
            )
            is None
        )
        assert repository.list_for_household(other_household.id) == []
    finally:
        db.close()


def test_repository_detects_normalized_alias_and_exclusion() -> None:
    db = create_test_session()
    try:
        user, household = create_dependencies(db, suffix="exists")
        repository = HouseholdGroceryAliasRepository(db)
        grocery_alias = repository.create(
            household_id=household.id,
            alias="Morning milk",
            normalized_alias="morning milk",
            canonical_key="milk",
            created_by_user_id=user.id,
        )

        assert repository.normalized_alias_exists(
            household_id=household.id,
            normalized_alias="morning milk",
        )
        assert not repository.normalized_alias_exists(
            household_id=household.id,
            normalized_alias="morning milk",
            excluding_alias_id=grocery_alias.id,
        )
    finally:
        db.close()


def test_repository_translates_create_and_update_duplicate_races() -> None:
    db = create_test_session()
    try:
        user, household = create_dependencies(db, suffix="duplicate")
        repository = HouseholdGroceryAliasRepository(db)
        first = repository.create(
            household_id=household.id,
            alias="Morning milk",
            normalized_alias="morning milk",
            canonical_key="milk",
            created_by_user_id=user.id,
        )
        second = repository.create(
            household_id=household.id,
            alias="Weekly rice",
            normalized_alias="weekly rice",
            canonical_key="rice",
            created_by_user_id=user.id,
        )

        with pytest.raises(DuplicateHouseholdGroceryAliasError):
            repository.create(
                household_id=household.id,
                alias="MORNING MILK",
                normalized_alias="morning milk",
                canonical_key="milk",
                created_by_user_id=user.id,
            )

        second.alias = "Morning milk"
        second.normalized_alias = "morning milk"
        with pytest.raises(DuplicateHouseholdGroceryAliasError):
            repository.update(second)
        db.refresh(second)
        assert second.normalized_alias == "weekly rice"
        assert first.normalized_alias == "morning milk"
    finally:
        db.close()


def test_repository_updates_and_deletes_alias() -> None:
    db = create_test_session()
    try:
        user, household = create_dependencies(db, suffix="mutate")
        repository = HouseholdGroceryAliasRepository(db)
        grocery_alias = repository.create(
            household_id=household.id,
            alias="Morning milk",
            normalized_alias="morning milk",
            canonical_key="milk",
            created_by_user_id=user.id,
        )
        alias_id = grocery_alias.id

        grocery_alias.alias = "Breakfast milk"
        grocery_alias.normalized_alias = "breakfast milk"
        updated = repository.update(grocery_alias)
        assert updated.alias == "Breakfast milk"

        repository.delete(updated)
        assert db.get(HouseholdGroceryAlias, alias_id) is None
    finally:
        db.close()


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_repository_rolls_back_unexpected_write_failures(operation: str) -> None:
    db = Mock(spec=Session)
    db.commit.side_effect = RuntimeError("database unavailable")
    repository = HouseholdGroceryAliasRepository(db)
    grocery_alias = HouseholdGroceryAlias(
        id=uuid4(),
        household_id=uuid4(),
        alias="Morning milk",
        normalized_alias="morning milk",
        canonical_key="milk",
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        if operation == "create":
            repository.create(
                household_id=grocery_alias.household_id,
                alias=grocery_alias.alias,
                normalized_alias=grocery_alias.normalized_alias,
                canonical_key=grocery_alias.canonical_key,
                created_by_user_id=uuid4(),
            )
        elif operation == "update":
            repository.update(grocery_alias)
        else:
            repository.delete(grocery_alias)

    db.rollback.assert_called_once_with()
