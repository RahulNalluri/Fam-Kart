from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    Household,
    HouseholdGroceryAlias,
    HouseholdMember,
    HouseholdRole,
    User,
)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    test_session = sessionmaker(bind=engine)
    Base.metadata.create_all(engine)
    with test_session() as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def create_user(db_session: Session, *, email: str) -> User:
    user = User(
        email=email,
        display_name="Household Alias API User",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_household(db_session: Session, *, name: str) -> Household:
    household = Household(name=name)
    db_session.add(household)
    db_session.commit()
    db_session.refresh(household)
    return household


def add_membership(
    db_session: Session,
    *,
    household: Household,
    user: User,
    role: HouseholdRole = HouseholdRole.MEMBER,
) -> None:
    db_session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role=role,
        ),
    )
    db_session.commit()


def create_alias(
    db_session: Session,
    *,
    household: Household,
    user: User,
    alias: str,
    canonical_key: str,
) -> HouseholdGroceryAlias:
    grocery_alias = HouseholdGroceryAlias(
        household_id=household.id,
        alias=alias,
        normalized_alias=alias.casefold(),
        canonical_key=canonical_key,
        created_by_user_id=user.id,
    )
    db_session.add(grocery_alias)
    db_session.commit()
    db_session.refresh(grocery_alias)
    return grocery_alias


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.parametrize("role", [HouseholdRole.OWNER, HouseholdRole.MEMBER])
def test_household_member_can_create_normalized_alias(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
) -> None:
    user = create_user(
        db_session,
        email=f"alias-api-create-{role.value}@example.com",
    )
    household = create_household(db_session, name="Alias API Family")
    add_membership(db_session, household=household, user=user, role=role)

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-aliases",
        headers=authorization_header(user),
        json={"alias": "  Morning   Milk  ", "canonical_key": "MILK"},
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["household_id"] == str(household.id)
    assert payload["alias"] == "Morning Milk"
    assert payload["canonical_key"] == "milk"
    assert payload["created_by_user_id"] == str(user.id)
    assert "normalized_alias" not in payload
    assert "created_at" in payload
    assert "updated_at" in payload


def test_member_lists_only_household_aliases_in_normalized_order(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="alias-api-list@example.com")
    household = create_household(db_session, name="Visible Aliases")
    hidden_household = create_household(db_session, name="Hidden Aliases")
    add_membership(db_session, household=household, user=member)
    create_alias(
        db_session,
        household=household,
        user=member,
        alias="Weekly rice",
        canonical_key="rice",
    )
    create_alias(
        db_session,
        household=household,
        user=member,
        alias="Breakfast milk",
        canonical_key="milk",
    )
    create_alias(
        db_session,
        household=hidden_household,
        user=member,
        alias="Hidden potato",
        canonical_key="potato",
    )

    response = client.get(
        f"/api/v1/households/{household.id}/grocery-aliases",
        headers=authorization_header(member),
    )

    assert response.status_code == 200
    assert [item["alias"] for item in response.json()] == [
        "Breakfast milk",
        "Weekly rice",
    ]
    assert all(item["household_id"] == str(household.id) for item in response.json())


def test_member_can_update_then_delete_household_alias(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="alias-api-lifecycle@example.com")
    household = create_household(db_session, name="Alias Lifecycle Family")
    add_membership(db_session, household=household, user=member)
    grocery_alias = create_alias(
        db_session,
        household=household,
        user=member,
        alias="Old family word",
        canonical_key="rice",
    )
    url = f"/api/v1/households/{household.id}/grocery-aliases/{grocery_alias.id}"
    headers = authorization_header(member)

    update_response = client.patch(
        url,
        headers=headers,
        json={"alias": "  New   family word ", "canonical_key": "DAL"},
    )

    assert update_response.status_code == 200
    assert update_response.json()["alias"] == "New family word"
    assert update_response.json()["canonical_key"] == "dal"

    delete_response = client.delete(url, headers=headers)

    assert delete_response.status_code == 204
    assert delete_response.content == b""
    assert db_session.get(HouseholdGroceryAlias, grocery_alias.id) is None


@pytest.mark.parametrize("method", ["post", "get"])
def test_outsider_and_unknown_household_return_same_error(
    client: TestClient,
    db_session: Session,
    method: str,
) -> None:
    outsider = create_user(db_session, email=f"alias-api-outsider-{method}@example.com")
    household = create_household(db_session, name="Private Alias Family")
    headers = authorization_header(outsider)
    request = getattr(client, method)
    request_kwargs = (
        {"json": {"alias": "Family rice", "canonical_key": "rice"}}
        if method == "post"
        else {}
    )

    outsider_response = request(
        f"/api/v1/households/{household.id}/grocery-aliases",
        headers=headers,
        **request_kwargs,
    )
    unknown_response = request(
        f"/api/v1/households/{uuid4()}/grocery-aliases",
        headers=headers,
        **request_kwargs,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


@pytest.mark.parametrize("method", ["patch", "delete"])
def test_cross_household_alias_id_is_not_exposed(
    client: TestClient,
    db_session: Session,
    method: str,
) -> None:
    member = create_user(
        db_session,
        email=f"alias-api-cross-household-{method}@example.com",
    )
    household = create_household(db_session, name="Member Alias Family")
    other_household = create_household(db_session, name="Other Alias Family")
    add_membership(db_session, household=household, user=member)
    grocery_alias = create_alias(
        db_session,
        household=other_household,
        user=member,
        alias="Other family rice",
        canonical_key="rice",
    )
    request = getattr(client, method)
    request_kwargs = {"json": {"alias": "Changed alias"}} if method == "patch" else {}

    response = request(
        f"/api/v1/households/{household.id}/grocery-aliases/{grocery_alias.id}",
        headers=authorization_header(member),
        **request_kwargs,
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == ("Household grocery alias not found.")


def test_duplicate_alias_returns_understandable_conflict(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="alias-api-duplicate@example.com")
    household = create_household(db_session, name="Duplicate Alias Family")
    add_membership(db_session, household=household, user=member)
    headers = authorization_header(member)
    url = f"/api/v1/households/{household.id}/grocery-aliases"
    assert (
        client.post(
            url,
            headers=headers,
            json={"alias": "Morning milk", "canonical_key": "milk"},
        ).status_code
        == 201
    )

    response = client.post(
        url,
        headers=headers,
        json={"alias": "  MORNING   MILK ", "canonical_key": "milk"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "This household already uses that grocery alias."
    )


@pytest.mark.parametrize(
    ("payload", "status_code", "message"),
    [
        (
            {"alias": "Cleaning liquid", "canonical_key": "dish_soap"},
            422,
            "Canonical grocery item is not supported.",
        ),
        (
            {"alias": "milk", "canonical_key": "rice"},
            409,
            "That standard grocery term belongs to another item.",
        ),
    ],
)
def test_create_rejects_invalid_alias_mappings(
    client: TestClient,
    db_session: Session,
    payload: dict[str, str],
    status_code: int,
    message: str,
) -> None:
    member = create_user(
        db_session,
        email=f"alias-api-invalid-{status_code}@example.com",
    )
    household = create_household(db_session, name="Validated Alias Family")
    add_membership(db_session, household=household, user=member)

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-aliases",
        headers=authorization_header(member),
        json=payload,
    )

    assert response.status_code == status_code
    assert response.json()["error"]["message"] == message


@pytest.mark.parametrize(
    ("method", "suffix", "payload"),
    [
        ("post", "", {"alias": "Family rice", "canonical_key": "rice"}),
        ("get", "", None),
        ("patch", f"/{uuid4()}", {"alias": "Changed family rice"}),
        ("delete", f"/{uuid4()}", None),
    ],
)
def test_alias_endpoints_require_authentication(
    client: TestClient,
    method: str,
    suffix: str,
    payload: dict[str, str] | None,
) -> None:
    response = client.request(
        method.upper(),
        f"/api/v1/households/{uuid4()}/grocery-aliases{suffix}",
        json=payload,
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Please log in again to continue."


@pytest.mark.parametrize(
    "payload",
    [
        {"alias": "   ", "canonical_key": "rice"},
        {"alias": "Family rice", "canonical_key": "   "},
        {"alias": "Family rice", "canonical_key": "rice", "extra": True},
    ],
)
def test_invalid_create_body_returns_standard_validation_error(
    client: TestClient,
    db_session: Session,
    payload: dict[str, object],
) -> None:
    member = create_user(
        db_session,
        email=f"alias-api-invalid-body-{uuid4()}@example.com",
    )
    household = create_household(db_session, name="Alias Body Validation Family")
    add_membership(db_session, household=household, user=member)

    response = client.post(
        f"/api/v1/households/{household.id}/grocery-aliases",
        headers=authorization_header(member),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Request validation failed."


def test_empty_update_body_returns_standard_validation_error(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="alias-api-empty-update@example.com")
    household = create_household(db_session, name="Alias Update Validation Family")
    add_membership(db_session, household=household, user=member)

    response = client.patch(
        f"/api/v1/households/{household.id}/grocery-aliases/{uuid4()}",
        headers=authorization_header(member),
        json={},
    )

    assert response.status_code == 422
    assert response.json()["error"]["message"] == "Request validation failed."
