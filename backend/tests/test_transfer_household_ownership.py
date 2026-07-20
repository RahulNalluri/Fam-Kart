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
        display_name="Ownership Transfer User",
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


def test_owner_can_transfer_ownership_and_then_leave(
    client: TestClient,
    db_session: Session,
) -> None:
    current_owner = create_user(db_session, email="transfer-owner@example.com")
    new_owner = create_user(db_session, email="transfer-member@example.com")
    household = create_household(db_session, name="Transfer Family")
    current_membership = add_membership(
        db_session,
        household=household,
        user=current_owner,
        role=HouseholdRole.OWNER,
    )
    new_membership = add_membership(
        db_session,
        household=household,
        user=new_owner,
        role=HouseholdRole.MEMBER,
    )

    response = client.patch(
        f"/api/v1/households/{household.id}/owner",
        headers=authorization_header(current_owner),
        json={"new_owner_user_id": str(new_owner.id)},
    )

    assert response.status_code == 204
    assert response.content == b""
    db_session.refresh(current_membership)
    db_session.refresh(new_membership)
    assert current_membership.role == HouseholdRole.MEMBER
    assert new_membership.role == HouseholdRole.OWNER

    leave_response = client.delete(
        f"/api/v1/households/{household.id}/members/me",
        headers=authorization_header(current_owner),
    )
    new_owner_leave_response = client.delete(
        f"/api/v1/households/{household.id}/members/me",
        headers=authorization_header(new_owner),
    )
    assert leave_response.status_code == 204
    assert new_owner_leave_response.status_code == 409
    assert db_session.get(HouseholdMember, current_membership.id) is None
    assert db_session.get(HouseholdMember, new_membership.id) is not None


def test_regular_member_cannot_transfer_ownership(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="protected-owner@example.com")
    member = create_user(db_session, email="protected-member@example.com")
    household = create_household(db_session, name="Protected Transfer Family")
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

    response = client.patch(
        f"/api/v1/households/{household.id}/owner",
        headers=authorization_header(member),
        json={"new_owner_user_id": str(owner.id)},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Only household owners can transfer ownership."
    )
    db_session.refresh(owner_membership)
    db_session.refresh(member_membership)
    assert owner_membership.role == HouseholdRole.OWNER
    assert member_membership.role == HouseholdRole.MEMBER


def test_owner_cannot_transfer_to_outsider(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="target-owner@example.com")
    outsider = create_user(db_session, email="target-outsider@example.com")
    household = create_household(db_session, name="Target Transfer Family")
    membership = add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )

    response = client.patch(
        f"/api/v1/households/{household.id}/owner",
        headers=authorization_header(owner),
        json={"new_owner_user_id": str(outsider.id)},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Household member not found."
    db_session.refresh(membership)
    assert membership.role == HouseholdRole.OWNER


def test_owner_cannot_transfer_ownership_to_self(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="self-transfer-owner@example.com")
    household = create_household(db_session, name="Self Transfer Family")
    membership = add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )

    response = client.patch(
        f"/api/v1/households/{household.id}/owner",
        headers=authorization_header(owner),
        json={"new_owner_user_id": str(owner.id)},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "Choose another household member as the new owner."
    )
    db_session.refresh(membership)
    assert membership.role == HouseholdRole.OWNER


def test_outsider_and_unknown_household_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="private-transfer-owner@example.com")
    outsider = create_user(db_session, email="private-transfer-outsider@example.com")
    household = create_household(db_session, name="Private Transfer Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    payload = {"new_owner_user_id": str(owner.id)}
    headers = authorization_header(outsider)

    outsider_response = client.patch(
        f"/api/v1/households/{household.id}/owner",
        headers=headers,
        json=payload,
    )
    unknown_response = client.patch(
        f"/api/v1/households/{uuid4()}/owner",
        headers=headers,
        json=payload,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["code"] == "http_404"
    assert unknown_response.json()["error"]["code"] == "http_404"
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


def test_transfer_ownership_requires_access_token(client: TestClient) -> None:
    response = client.patch(
        f"/api/v1/households/{uuid4()}/owner",
        json={"new_owner_user_id": str(uuid4())},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"new_owner_user_id": "not-a-uuid"},
        {"new_owner_user_id": str(uuid4()), "role": "owner"},
    ],
)
def test_transfer_ownership_rejects_invalid_request(
    client: TestClient,
    db_session: Session,
    payload: dict[str, str],
) -> None:
    owner = create_user(
        db_session,
        email=f"invalid-transfer-{uuid4()}@example.com",
    )

    response = client.patch(
        f"/api/v1/households/{uuid4()}/owner",
        headers=authorization_header(owner),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
