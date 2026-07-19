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
        display_name="Household Details User",
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


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (HouseholdRole.OWNER, "details-owner@example.com"),
        (HouseholdRole.MEMBER, "details-member@example.com"),
    ],
)
def test_household_member_can_view_details_with_own_role(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
    email: str,
) -> None:
    user = create_user(db_session, email=email)
    household = create_household(db_session, name="Details Family")
    membership = add_membership(
        db_session,
        household=household,
        user=user,
        role=role,
    )

    response = client.get(
        f"/api/v1/households/{household.id}",
        headers=authorization_header(user),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(household.id)
    assert response.json()["name"] == "Details Family"
    assert response.json()["role"] == role.value
    assert response.json()["joined_at"] == membership.joined_at.isoformat()
    assert "created_at" in response.json()
    assert "updated_at" in response.json()
    assert "email" not in response.json()
    assert "password_hash" not in response.json()
    assert "members" not in response.json()


def test_household_details_match_household_list_item(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="details-list@example.com")
    household = create_household(db_session, name="Consistent Family")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.MEMBER,
    )
    headers = authorization_header(user)

    details_response = client.get(
        f"/api/v1/households/{household.id}",
        headers=headers,
    )
    list_response = client.get("/api/v1/households", headers=headers)

    assert details_response.status_code == 200
    assert list_response.status_code == 200
    assert details_response.json() == list_response.json()[0]


def test_outsider_and_unknown_household_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="private-details-owner@example.com")
    outsider = create_user(db_session, email="private-details-outsider@example.com")
    household = create_household(db_session, name="Private Details Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    headers = authorization_header(outsider)

    outsider_response = client.get(
        f"/api/v1/households/{household.id}",
        headers=headers,
    )
    unknown_response = client.get(
        f"/api/v1/households/{uuid4()}",
        headers=headers,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["code"] == "http_404"
    assert unknown_response.json()["error"]["code"] == "http_404"
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


def test_household_details_requires_access_token(client: TestClient) -> None:
    response = client.get(f"/api/v1/households/{uuid4()}")

    assert response.status_code == 401


def test_household_details_rejects_malformed_id(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="details-malformed@example.com")

    response = client.get(
        "/api/v1/households/not-a-uuid",
        headers=authorization_header(user),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
