from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.invitations import hash_invitation_code
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.household import Household
from app.models.household_invitation import HouseholdInvitation
from app.models.household_member import HouseholdMember, HouseholdRole
from app.models.user import User

INVITATION_CODE = "FK-ABCD2345WXYZ"


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
        display_name="Household Join User",
        password_hash=hash_password("familykart123"),
        preferred_language="en",
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def create_household_with_owner(db_session: Session, owner: User) -> Household:
    household = Household(name="Join Test Family")
    db_session.add(household)
    db_session.flush()
    db_session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=owner.id,
            role=HouseholdRole.OWNER,
        ),
    )
    db_session.commit()
    db_session.refresh(household)
    return household


def create_invitation(
    db_session: Session,
    *,
    household: Household,
    owner: User,
    code: str = INVITATION_CODE,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
    used_by_user_id=None,
    revoked_at: datetime | None = None,
) -> HouseholdInvitation:
    invitation = HouseholdInvitation(
        household_id=household.id,
        created_by_user_id=owner.id,
        code_hash=hash_invitation_code(code),
        expires_at=expires_at or datetime.now(UTC) + timedelta(hours=24),
        used_at=used_at,
        used_by_user_id=used_by_user_id,
        revoked_at=revoked_at,
    )
    db_session.add(invitation)
    db_session.commit()
    db_session.refresh(invitation)
    return invitation


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_user_joins_household_and_invitation_is_consumed_atomically(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="join-owner@example.com")
    joining_user = create_user(db_session, email="joining-user@example.com")
    household = create_household_with_owner(db_session, owner)
    invitation = create_invitation(db_session, household=household, owner=owner)

    response = client.post(
        "/api/v1/households/join",
        headers=authorization_header(joining_user),
        json={"invitation_code": "  fk-abcd2345wxyz  "},
    )

    assert response.status_code == 201
    assert response.json()["id"] == str(household.id)
    assert response.json()["name"] == "Join Test Family"
    assert response.json()["role"] == "member"
    assert "joined_at" in response.json()

    membership = db_session.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == joining_user.id),
    )
    assert membership is not None
    assert membership.household_id == household.id
    assert membership.role == HouseholdRole.MEMBER
    db_session.refresh(invitation)
    assert invitation.used_at is not None
    assert invitation.used_by_user_id == joining_user.id

    list_response = client.get(
        "/api/v1/households",
        headers=authorization_header(joining_user),
    )
    assert list_response.status_code == 200
    assert list_response.json()[0]["id"] == str(household.id)
    assert list_response.json()[0]["role"] == "member"


def test_used_invitation_cannot_add_another_member(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="reuse-owner@example.com")
    first_user = create_user(db_session, email="first-join@example.com")
    second_user = create_user(db_session, email="second-join@example.com")
    household = create_household_with_owner(db_session, owner)
    create_invitation(db_session, household=household, owner=owner)
    payload = {"invitation_code": INVITATION_CODE}

    first_response = client.post(
        "/api/v1/households/join",
        headers=authorization_header(first_user),
        json=payload,
    )
    second_response = client.post(
        "/api/v1/households/join",
        headers=authorization_header(second_user),
        json=payload,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 400
    assert second_response.json()["error"]["message"] == (
        "Invitation code is invalid or unavailable."
    )
    second_membership = db_session.scalar(
        select(HouseholdMember).where(HouseholdMember.user_id == second_user.id),
    )
    assert second_membership is None


def test_existing_member_is_rejected_without_consuming_invitation(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="existing-owner@example.com")
    household = create_household_with_owner(db_session, owner)
    invitation = create_invitation(db_session, household=household, owner=owner)

    response = client.post(
        "/api/v1/households/join",
        headers=authorization_header(owner),
        json={"invitation_code": INVITATION_CODE},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "You are already a member of this household."
    )
    db_session.refresh(invitation)
    assert invitation.used_at is None
    assert invitation.used_by_user_id is None
    membership_count = db_session.scalar(
        select(func.count()).select_from(HouseholdMember),
    )
    assert membership_count == 1


@pytest.mark.parametrize("invitation_state", ["expired", "revoked", "used"])
def test_unavailable_invitation_states_return_same_safe_error(
    client: TestClient,
    db_session: Session,
    invitation_state: str,
) -> None:
    owner = create_user(db_session, email=f"{invitation_state}-owner@example.com")
    joining_user = create_user(
        db_session,
        email=f"{invitation_state}-joiner@example.com",
    )
    household = create_household_with_owner(db_session, owner)
    now = datetime.now(UTC)
    invitation_values = {
        "expires_at": (
            now - timedelta(seconds=1)
            if invitation_state == "expired"
            else now + timedelta(hours=24)
        ),
        "revoked_at": now if invitation_state == "revoked" else None,
        "used_at": now if invitation_state == "used" else None,
        "used_by_user_id": owner.id if invitation_state == "used" else None,
    }
    create_invitation(
        db_session,
        household=household,
        owner=owner,
        **invitation_values,
    )

    response = client.post(
        "/api/v1/households/join",
        headers=authorization_header(joining_user),
        json={"invitation_code": INVITATION_CODE},
    )

    assert response.status_code == 400
    assert response.json()["error"]["message"] == (
        "Invitation code is invalid or unavailable."
    )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"invitation_code": ""},
        {"invitation_code": "not-a-code"},
        {"invitation_code": INVITATION_CODE, "household_id": "injected"},
    ],
)
def test_join_household_rejects_invalid_request(
    client: TestClient,
    db_session: Session,
    payload: dict[str, str],
) -> None:
    user = create_user(db_session, email="invalid-join@example.com")

    response = client.post(
        "/api/v1/households/join",
        headers=authorization_header(user),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_join_household_requires_access_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/households/join",
        json={"invitation_code": INVITATION_CODE},
    )

    assert response.status_code == 401
