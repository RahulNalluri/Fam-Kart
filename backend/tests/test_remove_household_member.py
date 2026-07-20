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
from app.models.household import Household
from app.models.household_member import HouseholdMember, HouseholdRole
from app.models.user import User


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
        display_name="Member Removal User",
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
    role: HouseholdRole,
) -> HouseholdMember:
    membership = HouseholdMember(
        household_id=household.id,
        user_id=user.id,
        role=role,
    )
    db_session.add(membership)
    db_session.commit()
    db_session.refresh(membership)
    return membership


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_owner_can_remove_member_without_deleting_account(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="remove-owner@example.com")
    member = create_user(db_session, email="remove-member@example.com")
    household = create_household(db_session, name="Removal Family")
    owner_membership = add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    member_membership = add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    member_headers = authorization_header(member)

    response = client.delete(
        f"/api/v1/households/{household.id}/members/{member.id}",
        headers=authorization_header(owner),
    )

    assert response.status_code == 204
    assert response.content == b""
    assert db_session.get(HouseholdMember, member_membership.id) is None
    assert db_session.get(HouseholdMember, owner_membership.id) is not None
    assert db_session.get(Household, household.id) is not None
    assert db_session.get(User, member.id) is not None
    assert client.get("/api/v1/users/me", headers=member_headers).status_code == 200
    assert (
        client.get(
            f"/api/v1/households/{household.id}",
            headers=member_headers,
        ).status_code
        == 404
    )


def test_regular_member_cannot_remove_another_member(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="protected-remove-owner@example.com")
    requester = create_user(
        db_session,
        email="protected-remove-requester@example.com",
    )
    target = create_user(db_session, email="protected-remove-target@example.com")
    household = create_household(db_session, name="Protected Removal Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    add_membership(
        db_session,
        household=household,
        user=requester,
        role=HouseholdRole.MEMBER,
    )
    target_membership = add_membership(
        db_session,
        household=household,
        user=target,
        role=HouseholdRole.MEMBER,
    )

    response = client.delete(
        f"/api/v1/households/{household.id}/members/{target.id}",
        headers=authorization_header(requester),
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Only household owners can remove members."
    )
    assert db_session.get(HouseholdMember, target_membership.id) is not None


def test_owner_cannot_remove_outsider(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="target-remove-owner@example.com")
    outsider = create_user(db_session, email="target-remove-outsider@example.com")
    household = create_household(db_session, name="Target Removal Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )

    response = client.delete(
        f"/api/v1/households/{household.id}/members/{outsider.id}",
        headers=authorization_header(owner),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Household member not found."


def test_owner_cannot_remove_self(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="self-remove-owner@example.com")
    household = create_household(db_session, name="Self Removal Family")
    membership = add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )

    response = client.delete(
        f"/api/v1/households/{household.id}/members/{owner.id}",
        headers=authorization_header(owner),
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "Transfer ownership before removing the household owner."
    )
    assert db_session.get(HouseholdMember, membership.id) is not None


def test_outsider_and_unknown_household_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="private-remove-owner@example.com")
    outsider = create_user(db_session, email="private-remove-outsider@example.com")
    household = create_household(db_session, name="Private Removal Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    headers = authorization_header(outsider)

    outsider_response = client.delete(
        f"/api/v1/households/{household.id}/members/{owner.id}",
        headers=headers,
    )
    unknown_response = client.delete(
        f"/api/v1/households/{uuid4()}/members/{owner.id}",
        headers=headers,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["code"] == "http_404"
    assert unknown_response.json()["error"]["code"] == "http_404"
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


def test_remove_member_requires_access_token(client: TestClient) -> None:
    response = client.delete(
        f"/api/v1/households/{uuid4()}/members/{uuid4()}",
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        f"/api/v1/households/not-a-uuid/members/{uuid4()}",
        f"/api/v1/households/{uuid4()}/members/not-a-uuid",
    ],
)
def test_remove_member_rejects_malformed_ids(
    client: TestClient,
    db_session: Session,
    path: str,
) -> None:
    owner = create_user(
        db_session,
        email=f"invalid-remove-{uuid4()}@example.com",
    )

    response = client.delete(path, headers=authorization_header(owner))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
