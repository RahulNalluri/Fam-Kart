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


def create_user(
    db_session: Session,
    *,
    email: str,
    display_name: str,
    preferred_language: str = "en",
) -> User:
    user = User(
        email=email,
        display_name=display_name,
        password_hash=hash_password("familykart123"),
        preferred_language=preferred_language,
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


def test_household_member_can_list_members(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="members-owner@example.com",
        display_name="Anjali",
        preferred_language="te",
    )
    member = create_user(
        db_session,
        email="members-member@example.com",
        display_name="Rahul",
    )
    household = create_household(db_session, name="Members Family")
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

    response = client.get(
        f"/api/v1/households/{household.id}/members",
        headers=authorization_header(member),
    )

    assert response.status_code == 200
    assert response.json() == [
        {
            "user_id": str(owner.id),
            "display_name": "Anjali",
            "preferred_language": "te",
            "role": "owner",
            "joined_at": owner_membership.joined_at.isoformat(),
        },
        {
            "user_id": str(member.id),
            "display_name": "Rahul",
            "preferred_language": "en",
            "role": "member",
            "joined_at": member_membership.joined_at.isoformat(),
        },
    ]


def test_member_list_excludes_private_fields_and_other_households(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="isolated-members-owner@example.com",
        display_name="Owner",
    )
    other_user = create_user(
        db_session,
        email="other-household-member@example.com",
        display_name="Other User",
    )
    household = create_household(db_session, name="Requested Family")
    other_household = create_household(db_session, name="Other Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    add_membership(
        db_session,
        household=other_household,
        user=other_user,
        role=HouseholdRole.OWNER,
    )

    response = client.get(
        f"/api/v1/households/{household.id}/members",
        headers=authorization_header(owner),
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
    assert response.json()[0]["user_id"] == str(owner.id)
    assert "email" not in response.json()[0]
    assert "password_hash" not in response.json()[0]
    assert "is_active" not in response.json()[0]


def test_outsider_and_unknown_household_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(
        db_session,
        email="private-members-owner@example.com",
        display_name="Owner",
    )
    outsider = create_user(
        db_session,
        email="private-members-outsider@example.com",
        display_name="Outsider",
    )
    household = create_household(db_session, name="Private Members Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    headers = authorization_header(outsider)

    outsider_response = client.get(
        f"/api/v1/households/{household.id}/members",
        headers=headers,
    )
    unknown_response = client.get(
        f"/api/v1/households/{uuid4()}/members",
        headers=headers,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["code"] == "http_404"
    assert unknown_response.json()["error"]["code"] == "http_404"
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


def test_household_member_list_requires_access_token(client: TestClient) -> None:
    response = client.get(f"/api/v1/households/{uuid4()}/members")

    assert response.status_code == 401


def test_household_member_list_rejects_malformed_id(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(
        db_session,
        email="members-malformed@example.com",
        display_name="Malformed ID User",
    )

    response = client.get(
        "/api/v1/households/not-a-uuid/members",
        headers=authorization_header(user),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
