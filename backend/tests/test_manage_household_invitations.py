from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
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
        display_name="Invitation Manager",
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


def create_invitation(
    db_session: Session,
    *,
    household: Household,
    creator: User,
    code: str,
    expires_at: datetime,
    used_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> HouseholdInvitation:
    invitation = HouseholdInvitation(
        household_id=household.id,
        created_by_user_id=creator.id,
        code_hash=hash_invitation_code(code),
        expires_at=expires_at,
        used_at=used_at,
        revoked_at=revoked_at,
    )
    db_session.add(invitation)
    db_session.commit()
    db_session.refresh(invitation)
    return invitation


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def test_owner_lists_only_active_invitations_without_secrets(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    owner = create_user(db_session, email="list-invitations-owner@example.com")
    household = create_household(db_session, name="Invitation List Family")
    other_household = create_household(db_session, name="Other Invitation Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    first_active = create_invitation(
        db_session,
        household=household,
        creator=owner,
        code="FK-LSTA2345WXYZ",
        expires_at=now + timedelta(hours=1),
    )
    second_active = create_invitation(
        db_session,
        household=household,
        creator=owner,
        code="FK-LSTB2345WXYZ",
        expires_at=now + timedelta(hours=2),
    )
    create_invitation(
        db_session,
        household=household,
        creator=owner,
        code="FK-EXPD2345WXYZ",
        expires_at=now - timedelta(seconds=1),
    )
    create_invitation(
        db_session,
        household=household,
        creator=owner,
        code="FK-USED2345WXYZ",
        expires_at=now + timedelta(hours=3),
        used_at=now,
    )
    create_invitation(
        db_session,
        household=household,
        creator=owner,
        code="FK-REVK2345WXYZ",
        expires_at=now + timedelta(hours=3),
        revoked_at=now,
    )
    create_invitation(
        db_session,
        household=other_household,
        creator=owner,
        code="FK-OTHR2345WXYZ",
        expires_at=now + timedelta(hours=1),
    )

    response = client.get(
        f"/api/v1/households/{household.id}/invitations",
        headers=authorization_header(owner),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        str(first_active.id),
        str(second_active.id),
    ]
    for item in response.json():
        assert set(item) == {
            "id",
            "household_id",
            "created_by_user_id",
            "created_at",
            "expires_at",
        }
        assert item["household_id"] == str(household.id)
        assert "code" not in item
        assert "code_hash" not in item


def test_regular_member_cannot_list_invitations(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="list-invitations-member@example.com")
    household = create_household(db_session, name="Protected Invitation List")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )

    response = client.get(
        f"/api/v1/households/{household.id}/invitations",
        headers=authorization_header(member),
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Only household owners can view invitations."
    )


def test_outsider_and_unknown_household_cannot_list_invitations(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="private-list-owner@example.com")
    outsider = create_user(db_session, email="private-list-outsider@example.com")
    household = create_household(db_session, name="Private Invitation List")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    headers = authorization_header(outsider)

    outsider_response = client.get(
        f"/api/v1/households/{household.id}/invitations",
        headers=headers,
    )
    unknown_response = client.get(
        f"/api/v1/households/{uuid4()}/invitations",
        headers=headers,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


def test_owner_revokes_invitation_and_code_can_no_longer_join(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="revoke-owner@example.com")
    joining_user = create_user(db_session, email="revoked-code-user@example.com")
    household = create_household(db_session, name="Revocation Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    owner_headers = authorization_header(owner)
    create_response = client.post(
        f"/api/v1/households/{household.id}/invitations",
        headers=owner_headers,
    )
    invitation_id = create_response.json()["id"]
    code = create_response.json()["code"]

    response = client.delete(
        f"/api/v1/households/{household.id}/invitations/{invitation_id}",
        headers=owner_headers,
    )

    assert response.status_code == 204
    assert response.content == b""
    invitation = db_session.get(HouseholdInvitation, UUID(invitation_id))
    assert invitation is not None
    db_session.refresh(invitation)
    assert invitation.revoked_at is not None
    list_response = client.get(
        f"/api/v1/households/{household.id}/invitations",
        headers=owner_headers,
    )
    join_response = client.post(
        "/api/v1/households/join",
        headers=authorization_header(joining_user),
        json={"invitation_code": code},
    )
    second_revoke_response = client.delete(
        f"/api/v1/households/{household.id}/invitations/{invitation_id}",
        headers=owner_headers,
    )
    assert list_response.json() == []
    assert join_response.status_code == 400
    assert second_revoke_response.status_code == 404


def test_regular_member_cannot_revoke_invitation(
    client: TestClient,
    db_session: Session,
) -> None:
    now = datetime.now(UTC)
    owner = create_user(db_session, email="protected-revoke-owner@example.com")
    member = create_user(db_session, email="protected-revoke-member@example.com")
    household = create_household(db_session, name="Protected Revocation Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    invitation = create_invitation(
        db_session,
        household=household,
        creator=owner,
        code="FK-PROT2345WXYZ",
        expires_at=now + timedelta(hours=1),
    )

    response = client.delete(
        f"/api/v1/households/{household.id}/invitations/{invitation.id}",
        headers=authorization_header(member),
    )

    assert response.status_code == 403
    assert response.json()["error"]["message"] == (
        "Only household owners can revoke invitations."
    )
    db_session.refresh(invitation)
    assert invitation.revoked_at is None


def test_invitation_from_another_household_cannot_be_revoked(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="cross-household-revoke@example.com")
    household = create_household(db_session, name="Revocation Scope Family")
    other_household = create_household(db_session, name="Other Revocation Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    invitation = create_invitation(
        db_session,
        household=other_household,
        creator=owner,
        code="FK-CROS2345WXYZ",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )

    response = client.delete(
        f"/api/v1/households/{household.id}/invitations/{invitation.id}",
        headers=authorization_header(owner),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Active invitation not found."
    db_session.refresh(invitation)
    assert invitation.revoked_at is None


@pytest.mark.parametrize("state", ["expired", "used", "revoked"])
def test_inactive_invitation_cannot_be_revoked(
    client: TestClient,
    db_session: Session,
    state: str,
) -> None:
    now = datetime.now(UTC).replace(microsecond=0)
    owner = create_user(
        db_session,
        email=f"inactive-{state}-revoke@example.com",
    )
    household = create_household(db_session, name="Inactive Revocation Family")
    add_membership(
        db_session,
        household=household,
        user=owner,
        role=HouseholdRole.OWNER,
    )
    invitation = create_invitation(
        db_session,
        household=household,
        creator=owner,
        code=f"FK-{state[:4].upper()}2345WXYZ",
        expires_at=(
            now - timedelta(seconds=1)
            if state == "expired"
            else now + timedelta(hours=1)
        ),
        used_at=now if state == "used" else None,
        revoked_at=now if state == "revoked" else None,
    )

    response = client.delete(
        f"/api/v1/households/{household.id}/invitations/{invitation.id}",
        headers=authorization_header(owner),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Active invitation not found."


@pytest.mark.parametrize("method", ["GET", "DELETE"])
def test_manage_invitations_requires_access_token(
    client: TestClient,
    method: str,
) -> None:
    path = f"/api/v1/households/{uuid4()}/invitations"
    if method == "DELETE":
        path += f"/{uuid4()}"

    response = client.request(method, path)

    assert response.status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/households/not-a-uuid/invitations",
        f"/api/v1/households/{uuid4()}/invitations/not-a-uuid",
    ],
)
def test_manage_invitations_rejects_malformed_ids(
    client: TestClient,
    db_session: Session,
    path: str,
) -> None:
    owner = create_user(
        db_session,
        email=f"malformed-invitation-{uuid4()}@example.com",
    )
    method = (
        "DELETE" if path.endswith("not-a-uuid") and "invitations/" in path else "GET"
    )

    response = client.request(method, path, headers=authorization_header(owner))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
