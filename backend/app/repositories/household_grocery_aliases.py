from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.household_grocery_alias import HouseholdGroceryAlias

ALIAS_UNIQUE_CONSTRAINT = "uq_household_grocery_aliases_household_normalized_alias"


class DuplicateHouseholdGroceryAliasError(ValueError):
    pass


class HouseholdGroceryAliasRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        household_id: UUID,
        alias: str,
        normalized_alias: str,
        canonical_key: str,
        created_by_user_id: UUID,
    ) -> HouseholdGroceryAlias:
        grocery_alias = HouseholdGroceryAlias(
            household_id=household_id,
            alias=alias,
            normalized_alias=normalized_alias,
            canonical_key=canonical_key,
            created_by_user_id=created_by_user_id,
        )
        try:
            self.db.add(grocery_alias)
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            if _is_alias_conflict(error):
                raise DuplicateHouseholdGroceryAliasError from error
            raise
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(grocery_alias)
        return grocery_alias

    def get_for_household(
        self,
        *,
        alias_id: UUID,
        household_id: UUID,
    ) -> HouseholdGroceryAlias | None:
        statement = select(HouseholdGroceryAlias).where(
            HouseholdGroceryAlias.id == alias_id,
            HouseholdGroceryAlias.household_id == household_id,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_for_household(self, household_id: UUID) -> list[HouseholdGroceryAlias]:
        statement = (
            select(HouseholdGroceryAlias)
            .where(HouseholdGroceryAlias.household_id == household_id)
            .order_by(
                HouseholdGroceryAlias.normalized_alias.asc(),
                HouseholdGroceryAlias.id.asc(),
            )
        )
        return list(self.db.execute(statement).scalars().all())

    def normalized_alias_exists(
        self,
        *,
        household_id: UUID,
        normalized_alias: str,
        excluding_alias_id: UUID | None = None,
    ) -> bool:
        statement = select(HouseholdGroceryAlias.id).where(
            HouseholdGroceryAlias.household_id == household_id,
            HouseholdGroceryAlias.normalized_alias == normalized_alias,
        )
        if excluding_alias_id is not None:
            statement = statement.where(HouseholdGroceryAlias.id != excluding_alias_id)
        statement = statement.execution_options(autoflush=False)
        return self.db.execute(statement).first() is not None

    def update(self, grocery_alias: HouseholdGroceryAlias) -> HouseholdGroceryAlias:
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            if _is_alias_conflict(error):
                raise DuplicateHouseholdGroceryAliasError from error
            raise
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(grocery_alias)
        return grocery_alias

    def delete(self, grocery_alias: HouseholdGroceryAlias) -> None:
        try:
            self.db.delete(grocery_alias)
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise


def _is_alias_conflict(error: IntegrityError) -> bool:
    diagnostic = getattr(error.orig, "diag", None)
    constraint_name = getattr(diagnostic, "constraint_name", None)
    return constraint_name == ALIAS_UNIQUE_CONSTRAINT or (
        ALIAS_UNIQUE_CONSTRAINT in str(error.orig)
        or "household_grocery_aliases.household_id, "
        "household_grocery_aliases.normalized_alias" in str(error.orig)
    )
