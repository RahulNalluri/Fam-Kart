import re
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.invitations import hash_invitation_code
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.household import Household
from app.models.household_invitation import HouseholdInvitation
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
        display_name="Invitation Creator",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_household_membership(
    db_session: Session,
    *,
    user: User,
    role: HouseholdRole,
) -> Household:
    household = Household(name="Invitation API Family")
    db_session.add(household)
    db_session.flush()
    db_session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role=role,
        ),
    )
    db_session.commit()
    db_session.refresh(household)
    return household


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_owner_creates_invitation_and_only_hash_is_stored(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="owner@example.com")
    household = create_household_membership(
        db_session,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    requested_at = datetime.now(UTC)

    response = client.post(
        f"/api/v1/households/{household.id}/invitations",
        headers=authorization_header(owner),
    )

    assert response.status_code == 201
    assert response.json()["household_id"] == str(household.id)
    assert re.fullmatch(r"FK-[A-HJ-NP-Z2-9]{12}", response.json()["code"])
    invitation = db_session.scalar(select(HouseholdInvitation))
    assert invitation is not None
    assert response.json()["id"] == str(invitation.id)
    assert invitation.household_id == household.id
    assert invitation.created_by_user_id == owner.id
    assert invitation.code_hash == hash_invitation_code(response.json()["code"])
    assert invitation.code_hash != response.json()["code"]
    expected_expiration = requested_at + timedelta(
        hours=settings.household_invitation_expire_hours,
    )
    actual_expiration = datetime.fromisoformat(response.json()["expires_at"])
    if actual_expiration.tzinfo is None:
        actual_expiration = actual_expiration.replace(tzinfo=UTC)
    assert (
        expected_expiration
        <= actual_expiration
        <= expected_expiration
        + timedelta(
            seconds=5,
        )
    )


def test_owner_can_create_distinct_one_time_invitations(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="multiple-owner@example.com")
    household = create_household_membership(
        db_session,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    url = f"/api/v1/households/{household.id}/invitations"
    headers = authorization_header(owner)

    first_response = client.post(url, headers=headers)
    second_response = client.post(url, headers=headers)

    assert first_response.status_code == 201
    assert second_response.status_code == 201
    assert first_response.json()["code"] != second_response.json()["code"]
    invitations = db_session.scalars(select(HouseholdInvitation)).all()
    assert len(invitations) == 2
    assert invitations[0].code_hash != invitations[1].code_hash


def test_regular_member_can_create_invitation(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="member@example.com")
    household = create_household_membership(
        db_session,
        user=member,
        role=HouseholdRole.MEMBER,
    )

    response = client.post(
        f"/api/v1/households/{household.id}/invitations",
        headers=authorization_header(member),
    )

    assert response.status_code == 201
    invitation = db_session.scalar(select(HouseholdInvitation))
    assert invitation is not None
    assert invitation.household_id == household.id
    assert invitation.created_by_user_id == member.id
    assert invitation.code_hash == hash_invitation_code(response.json()["code"])


def test_outsider_cannot_discover_or_invite_to_household(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="private-owner@example.com")
    outsider = create_user(db_session, email="outsider@example.com")
    household = create_household_membership(
        db_session,
        user=owner,
        role=HouseholdRole.OWNER,
    )

    response = client.post(
        f"/api/v1/households/{household.id}/invitations",
        headers=authorization_header(outsider),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Household not found."
    assert db_session.scalar(select(HouseholdInvitation)) is None


def test_unknown_household_returns_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="unknown-household@example.com")

    response = client.post(
        f"/api/v1/households/{uuid4()}/invitations",
        headers=authorization_header(user),
    )

    assert response.status_code == 404


def test_create_invitation_requires_access_token(client: TestClient) -> None:
    response = client.post(f"/api/v1/households/{uuid4()}/invitations")

    assert response.status_code == 401


def test_create_invitation_rejects_malformed_household_id(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="malformed-id@example.com")

    response = client.post(
        "/api/v1/households/not-a-uuid/invitations",
        headers=authorization_header(user),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
