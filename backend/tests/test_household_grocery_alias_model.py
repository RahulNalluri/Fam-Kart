from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.household import Household
from app.models.household_grocery_alias import HouseholdGroceryAlias


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine)
    with test_session() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_household_grocery_alias_columns_and_constraints() -> None:
    table = HouseholdGroceryAlias.__table__
    columns = table.columns

    assert set(columns.keys()) == {
        "id",
        "household_id",
        "alias",
        "normalized_alias",
        "canonical_key",
        "created_by_user_id",
        "created_at",
        "updated_at",
    }
    assert columns["alias"].type.length == 160
    assert columns["normalized_alias"].type.length == 160
    assert columns["canonical_key"].type.length == 64
    assert columns["created_by_user_id"].nullable is True
    assert {
        constraint.name for constraint in table.constraints if constraint.name
    }.issuperset(
        {
            "ck_household_grocery_aliases_alias_not_blank",
            "ck_household_grocery_aliases_normalized_alias_not_blank",
            "ck_household_grocery_aliases_canonical_key_not_blank",
            "uq_household_grocery_aliases_household_normalized_alias",
        },
    )
    assert {index.name for index in table.indexes}.issuperset(
        {
            "ix_household_grocery_aliases_created_by_user_id",
            "ix_household_grocery_aliases_household_canonical_key",
        },
    )


def test_alias_is_unique_only_within_its_household(db_session: Session) -> None:
    first_household = Household(name="First Family")
    second_household = Household(name="Second Family")
    db_session.add_all([first_household, second_household])
    db_session.flush()
    db_session.add_all(
        [
            HouseholdGroceryAlias(
                household_id=first_household.id,
                alias="Morning milk",
                normalized_alias="morning milk",
                canonical_key="milk",
            ),
            HouseholdGroceryAlias(
                household_id=second_household.id,
                alias="Morning milk",
                normalized_alias="morning milk",
                canonical_key="milk",
            ),
        ],
    )
    db_session.commit()

    db_session.add(
        HouseholdGroceryAlias(
            household_id=first_household.id,
            alias="MORNING MILK",
            normalized_alias="morning milk",
            canonical_key="milk",
        ),
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("alias", "  "),
        ("normalized_alias", ""),
        ("canonical_key", "   "),
    ],
)
def test_alias_text_fields_cannot_be_blank(
    db_session: Session,
    field: str,
    value: str,
) -> None:
    household = Household(name=f"Blank {field}")
    db_session.add(household)
    db_session.flush()
    values = {
        "household_id": household.id,
        "alias": "Family term",
        "normalized_alias": "family term",
        "canonical_key": "rice",
        field: value,
    }
    db_session.add(HouseholdGroceryAlias(**values))

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_deleting_household_removes_its_aliases(db_session: Session) -> None:
    household = Household(name="Cascade Family")
    household.grocery_aliases.append(
        HouseholdGroceryAlias(
            alias="Weekly item",
            normalized_alias="weekly item",
            canonical_key="rice",
        ),
    )
    db_session.add(household)
    db_session.commit()
    alias_id = household.grocery_aliases[0].id

    db_session.delete(household)
    db_session.commit()

    assert (
        db_session.scalar(
            select(HouseholdGroceryAlias).where(HouseholdGroceryAlias.id == alias_id),
        )
        is None
    )
