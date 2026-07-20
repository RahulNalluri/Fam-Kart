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
        display_name="Household Rename User",
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


def test_owner_can_rename_only_selected_household(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="rename-owner@example.com")
    household = create_household(db_session, name="Old Family Name")
    other_household = create_household(db_session, name="Unchanged Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    add_membership(
        db_session,
        household=other_household,
        user=owner,
        role=HouseholdRole.OWNER,
    )

    response = client.patch(
        f"/api/v1/households/{household.id}",
        headers=authorization_header(owner),
        json={"name": "   Nalluri Family   "},
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(household.id)
    assert response.json()["name"] == "Nalluri Family"
    assert "created_at" in response.json()
    assert "updated_at" in response.json()
    db_session.refresh(household)
    db_session.refresh(other_household)
    assert household.name == "Nalluri Family"
    assert other_household.name == "Unchanged Family"


def test_regular_member_cannot_rename_household(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="rename-member@example.com")
    household = create_household(db_session, name="Protected Family")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )

    response = client.patch(
        f"/api/v1/households/{household.id}",
        headers=authorization_header(member),
        json={"name": "Unauthorized Name"},
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Only household owners can rename the household."
    )
    db_session.refresh(household)
    assert household.name == "Protected Family"


def test_outsider_and_unknown_household_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="private-rename-owner@example.com")
    outsider = create_user(db_session, email="private-rename-outsider@example.com")
    household = create_household(db_session, name="Private Rename Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    headers = authorization_header(outsider)
    payload = {"name": "Disallowed Rename"}

    outsider_response = client.patch(
        f"/api/v1/households/{household.id}",
        headers=headers,
        json=payload,
    )
    unknown_response = client.patch(
        f"/api/v1/households/{uuid4()}",
        headers=headers,
        json=payload,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["code"] == "http_404"
    assert unknown_response.json()["error"]["code"] == "http_404"
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."
    db_session.refresh(household)
    assert household.name == "Private Rename Family"


def test_rename_household_requires_access_token(client: TestClient) -> None:
    response = client.patch(
        f"/api/v1/households/{uuid4()}",
        json={"name": "No Authentication"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 121},
        {"name": "Valid Name", "owner_id": str(uuid4())},
    ],
)
def test_rename_household_rejects_invalid_request(
    client: TestClient,
    db_session: Session,
    payload: dict[str, str],
) -> None:
    owner = create_user(
        db_session,
        email=f"invalid-rename-{uuid4()}@example.com",
    )

    response = client.patch(
        f"/api/v1/households/{uuid4()}",
        headers=authorization_header(owner),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_rename_household_rejects_malformed_id(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="malformed-rename@example.com")

    response = client.patch(
        "/api/v1/households/not-a-uuid",
        headers=authorization_header(owner),
        json={"name": "Valid Name"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
