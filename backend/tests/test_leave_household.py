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
        display_name="Leave Household User",
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


def test_member_can_leave_without_deleting_account_or_household(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="leave-owner@example.com")
    member = create_user(db_session, email="leave-member@example.com")
    household = create_household(db_session, name="Leave Family")
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
    headers = authorization_header(member)

    response = client.delete(
        f"/api/v1/households/{household.id}/members/me",
        headers=headers,
    )

    assert response.status_code == 204
    assert response.content == b""
    assert db_session.get(HouseholdMember, member_membership.id) is None
    assert db_session.get(HouseholdMember, owner_membership.id) is not None
    assert db_session.get(Household, household.id) is not None
    assert db_session.get(User, member.id) is not None
    assert client.get("/api/v1/users/me", headers=headers).status_code == 200
    assert client.get("/api/v1/households", headers=headers).json() == []

    second_response = client.delete(
        f"/api/v1/households/{household.id}/members/me",
        headers=headers,
    )
    assert second_response.status_code == 404


def test_owner_must_transfer_ownership_before_leaving(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="blocked-leave-owner@example.com")
    household = create_household(db_session, name="Owned Family")
    membership = add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )

    response = client.delete(
        f"/api/v1/households/{household.id}/members/me",
        headers=authorization_header(owner),
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "Transfer household ownership before leaving the household."
    )
    assert db_session.get(HouseholdMember, membership.id) is not None


def test_outsider_and_unknown_household_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="private-leave-owner@example.com")
    outsider = create_user(db_session, email="private-leave-outsider@example.com")
    household = create_household(db_session, name="Private Leave Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    headers = authorization_header(outsider)

    outsider_response = client.delete(
        f"/api/v1/households/{household.id}/members/me",
        headers=headers,
    )
    unknown_response = client.delete(
        f"/api/v1/households/{uuid4()}/members/me",
        headers=headers,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["code"] == "http_404"
    assert unknown_response.json()["error"]["code"] == "http_404"
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


def test_leave_household_requires_access_token(client: TestClient) -> None:
    response = client.delete(f"/api/v1/households/{uuid4()}/members/me")

    assert response.status_code == 401


def test_leave_household_rejects_malformed_id(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="leave-malformed@example.com")

    response = client.delete(
        "/api/v1/households/not-a-uuid/members/me",
        headers=authorization_header(user),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
