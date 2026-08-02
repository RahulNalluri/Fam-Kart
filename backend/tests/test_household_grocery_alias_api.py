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


def test_complete_household_alias_collaboration_workflow(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="alias-workflow-owner@example.com")
    member = create_user(db_session, email="alias-workflow-member@example.com")
    household = create_household(db_session, name="Alias Workflow Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    add_membership(db_session, household=household, user=member)
    collection_url = f"/api/v1/households/{household.id}/grocery-aliases"

    created = client.post(
        collection_url,
        headers=authorization_header(owner),
        json={"alias": "  Family   breakfast ", "canonical_key": "milk"},
    )
    assert created.status_code == 201
    alias_id = created.json()["id"]
    alias_url = f"{collection_url}/{alias_id}"

    member_list = client.get(
        collection_url,
        headers=authorization_header(member),
    )
    assert member_list.status_code == 200
    assert [entry["id"] for entry in member_list.json()] == [alias_id]

    updated = client.patch(
        alias_url,
        headers=authorization_header(member),
        json={"alias": "Weekend breakfast", "canonical_key": "egg"},
    )
    assert updated.status_code == 200
    assert updated.json()["alias"] == "Weekend breakfast"
    assert updated.json()["canonical_key"] == "egg"
    assert updated.json()["created_by_user_id"] == str(owner.id)

    owner_list = client.get(
        collection_url,
        headers=authorization_header(owner),
    )
    assert owner_list.status_code == 200
    assert owner_list.json()[0]["alias"] == "Weekend breakfast"
    assert owner_list.json()[0]["canonical_key"] == "egg"

    deleted = client.delete(
        alias_url,
        headers=authorization_header(owner),
    )
    assert deleted.status_code == 204
    assert (
        client.get(
            collection_url,
            headers=authorization_header(member),
        ).json()
        == []
    )


@pytest.mark.parametrize("action", ["create", "list", "update", "delete"])
def test_removed_member_loses_all_alias_access_immediately(
    client: TestClient,
    db_session: Session,
    action: str,
) -> None:
    owner = create_user(
        db_session,
        email=f"alias-revocation-owner-{action}@example.com",
    )
    former_member = create_user(
        db_session,
        email=f"alias-revocation-member-{action}@example.com",
    )
    household = create_household(db_session, name=f"Alias Revocation {action}")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    add_membership(db_session, household=household, user=former_member)
    grocery_alias = create_alias(
        db_session,
        household=household,
        user=owner,
        alias="Shared family rice",
        canonical_key="rice",
    )
    collection_url = f"/api/v1/households/{household.id}/grocery-aliases"
    alias_url = f"{collection_url}/{grocery_alias.id}"

    removed = client.delete(
        f"/api/v1/households/{household.id}/members/{former_member.id}",
        headers=authorization_header(owner),
    )
    assert removed.status_code == 204

    if action == "create":
        response = client.post(
            collection_url,
            headers=authorization_header(former_member),
            json={"alias": "Blocked family milk", "canonical_key": "milk"},
        )
    elif action == "list":
        response = client.get(
            collection_url,
            headers=authorization_header(former_member),
        )
    elif action == "update":
        response = client.patch(
            alias_url,
            headers=authorization_header(former_member),
            json={"alias": "Blocked family rice"},
        )
    else:
        response = client.delete(
            alias_url,
            headers=authorization_header(former_member),
        )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Household not found."
    db_session.expire_all()
    stored_alias = db_session.get(HouseholdGroceryAlias, grocery_alias.id)
    assert stored_alias is not None
    assert stored_alias.alias == "Shared family rice"
    assert db_session.query(HouseholdGroceryAlias).count() == 1


@pytest.mark.parametrize(
    ("update_payload", "status_code", "message"),
    [
        (
            {"alias": "Existing family milk"},
            409,
            "This household already uses that grocery alias.",
        ),
        (
            {"canonical_key": "dish_soap"},
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
def test_rejected_alias_update_preserves_stored_mapping(
    client: TestClient,
    db_session: Session,
    update_payload: dict[str, str],
    status_code: int,
    message: str,
) -> None:
    member = create_user(
        db_session,
        email=f"alias-rejected-update-{uuid4()}@example.com",
    )
    household = create_household(db_session, name="Rejected Alias Update Family")
    add_membership(db_session, household=household, user=member)
    grocery_alias = create_alias(
        db_session,
        household=household,
        user=member,
        alias="Original family rice",
        canonical_key="rice",
    )
    create_alias(
        db_session,
        household=household,
        user=member,
        alias="Existing family milk",
        canonical_key="milk",
    )
    alias_url = f"/api/v1/households/{household.id}/grocery-aliases/{grocery_alias.id}"

    response = client.patch(
        alias_url,
        headers=authorization_header(member),
        json=update_payload,
    )

    assert response.status_code == status_code
    assert response.json()["error"]["message"] == message
    db_session.expire_all()
    stored_alias = db_session.get(HouseholdGroceryAlias, grocery_alias.id)
    assert stored_alias is not None
    assert stored_alias.alias == "Original family rice"
    assert stored_alias.normalized_alias == "original family rice"
    assert stored_alias.canonical_key == "rice"


def test_same_normalized_alias_can_be_used_by_separate_households(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="alias-household-scope@example.com")
    first_household = create_household(db_session, name="First Scoped Alias Family")
    second_household = create_household(db_session, name="Second Scoped Alias Family")
    add_membership(db_session, household=first_household, user=member)
    add_membership(db_session, household=second_household, user=member)
    headers = authorization_header(member)

    first_response = client.post(
        f"/api/v1/households/{first_household.id}/grocery-aliases",
        headers=headers,
        json={"alias": "Morning milk", "canonical_key": "milk"},
    )
    second_response = client.post(
        f"/api/v1/households/{second_household.id}/grocery-aliases",
        headers=headers,
        json={"alias": "  MORNING   MILK ", "canonical_key": "milk"},
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["household_id"] == str(first_household.id)
    assert second_response.json()["household_id"] == str(second_household.id)
    assert first_response.json()["id"] != second_response.json()["id"]
