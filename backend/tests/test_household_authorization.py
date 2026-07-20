from collections.abc import Generator
from dataclasses import dataclass
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app

PASSWORD = "familykart123"


@dataclass(frozen=True)
class AuthorizationAccount:
    id: str
    access_token: str

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}"}


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


def create_account(client: TestClient, *, label: str) -> AuthorizationAccount:
    email = f"authorization-{label}-{uuid4()}@example.com"
    register_response = client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "display_name": f"Authorization {label}",
            "password": PASSWORD,
            "preferred_language": "en",
        },
    )
    assert register_response.status_code == 201
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert login_response.status_code == 200
    return AuthorizationAccount(
        id=register_response.json()["id"],
        access_token=login_response.json()["access_token"],
    )


def create_household(
    client: TestClient,
    *,
    owner: AuthorizationAccount,
    name: str,
) -> str:
    response = client.post(
        "/api/v1/households",
        headers=owner.headers,
        json={"name": name},
    )
    assert response.status_code == 201
    return response.json()["id"]


def create_invitation(
    client: TestClient,
    *,
    owner: AuthorizationAccount,
    household_id: str,
) -> dict[str, str]:
    response = client.post(
        f"/api/v1/households/{household_id}/invitations",
        headers=owner.headers,
    )
    assert response.status_code == 201
    return response.json()


def join_household(
    client: TestClient,
    *,
    account: AuthorizationAccount,
    invitation_code: str,
) -> None:
    response = client.post(
        "/api/v1/households/join",
        headers=account.headers,
        json={"invitation_code": invitation_code},
    )
    assert response.status_code == 201


def test_owner_member_and_outsider_permission_matrix(client: TestClient) -> None:
    owner = create_account(client, label="matrix-owner")
    member = create_account(client, label="matrix-member")
    other_owner = create_account(client, label="matrix-other-owner")
    household_id = create_household(
        client,
        owner=owner,
        name="Authorization Matrix Family",
    )
    other_household_id = create_household(
        client,
        owner=other_owner,
        name="Separate Authorization Family",
    )
    invitation = create_invitation(
        client,
        owner=owner,
        household_id=household_id,
    )
    join_household(
        client,
        account=member,
        invitation_code=invitation["code"],
    )

    for account in (owner, member):
        assert (
            client.get(
                f"/api/v1/households/{household_id}",
                headers=account.headers,
            ).status_code
            == 200
        )
        assert (
            client.get(
                f"/api/v1/households/{household_id}/members",
                headers=account.headers,
            ).status_code
            == 200
        )

    member_invitation_response = client.post(
        f"/api/v1/households/{household_id}/invitations",
        headers=member.headers,
    )
    assert member_invitation_response.status_code == 201

    member_only_owner_requests = [
        ("PATCH", f"/api/v1/households/{household_id}", {"name": "Denied"}),
        ("GET", f"/api/v1/households/{household_id}/invitations", None),
        (
            "PATCH",
            f"/api/v1/households/{household_id}/owner",
            {"new_owner_user_id": owner.id},
        ),
        (
            "DELETE",
            f"/api/v1/households/{household_id}/members/{owner.id}",
            None,
        ),
        (
            "DELETE",
            f"/api/v1/households/{household_id}/invitations/{invitation['id']}",
            None,
        ),
    ]
    for method, path, payload in member_only_owner_requests:
        response = client.request(
            method,
            path,
            headers=member.headers,
            json=payload,
        )
        assert response.status_code == 403

    outsider_requests = [
        ("GET", f"/api/v1/households/{household_id}", None),
        ("GET", f"/api/v1/households/{household_id}/members", None),
        ("PATCH", f"/api/v1/households/{household_id}", {"name": "Denied"}),
        ("POST", f"/api/v1/households/{household_id}/invitations", None),
        ("GET", f"/api/v1/households/{household_id}/invitations", None),
        (
            "PATCH",
            f"/api/v1/households/{household_id}/owner",
            {"new_owner_user_id": member.id},
        ),
        (
            "DELETE",
            f"/api/v1/households/{household_id}/members/{member.id}",
            None,
        ),
        (
            "DELETE",
            f"/api/v1/households/{household_id}/invitations/{invitation['id']}",
            None,
        ),
    ]
    for method, path, payload in outsider_requests:
        response = client.request(
            method,
            path,
            headers=other_owner.headers,
            json=payload,
        )
        assert response.status_code == 404
        assert response.json()["error"]["message"] == "Household not found."

    cross_household_response = client.get(
        f"/api/v1/households/{other_household_id}",
        headers=owner.headers,
    )
    assert cross_household_response.status_code == 404


def test_ownership_transfer_changes_permissions_immediately(
    client: TestClient,
) -> None:
    previous_owner = create_account(client, label="previous-owner")
    new_owner = create_account(client, label="new-owner")
    household_id = create_household(
        client,
        owner=previous_owner,
        name="Ownership Permission Family",
    )
    invitation = create_invitation(
        client,
        owner=previous_owner,
        household_id=household_id,
    )
    join_household(
        client,
        account=new_owner,
        invitation_code=invitation["code"],
    )

    transfer_response = client.patch(
        f"/api/v1/households/{household_id}/owner",
        headers=previous_owner.headers,
        json={"new_owner_user_id": new_owner.id},
    )
    assert transfer_response.status_code == 204

    old_owner_details = client.get(
        f"/api/v1/households/{household_id}",
        headers=previous_owner.headers,
    )
    assert old_owner_details.status_code == 200
    assert old_owner_details.json()["role"] == "member"
    assert (
        client.patch(
            f"/api/v1/households/{household_id}",
            headers=previous_owner.headers,
            json={"name": "Old Owner Rename"},
        ).status_code
        == 403
    )
    previous_owner_invitation_response = client.post(
        f"/api/v1/households/{household_id}/invitations",
        headers=previous_owner.headers,
    )
    assert previous_owner_invitation_response.status_code == 201
    assert (
        client.delete(
            f"/api/v1/households/{household_id}/members/{new_owner.id}",
            headers=previous_owner.headers,
        ).status_code
        == 403
    )

    rename_response = client.patch(
        f"/api/v1/households/{household_id}",
        headers=new_owner.headers,
        json={"name": "New Owner Family"},
    )
    new_invitation_response = client.post(
        f"/api/v1/households/{household_id}/invitations",
        headers=new_owner.headers,
    )
    remove_response = client.delete(
        f"/api/v1/households/{household_id}/members/{previous_owner.id}",
        headers=new_owner.headers,
    )
    assert rename_response.status_code == 200
    assert new_invitation_response.status_code == 201
    assert remove_response.status_code == 204
    assert (
        client.get(
            f"/api/v1/households/{household_id}",
            headers=previous_owner.headers,
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/households/{household_id}/invitations",
            headers=previous_owner.headers,
        ).status_code
        == 404
    )
    assert (
        client.get("/api/v1/users/me", headers=previous_owner.headers).status_code
        == 200
    )


def test_member_can_leave_and_rejoin_only_with_new_invitation(
    client: TestClient,
) -> None:
    owner = create_account(client, label="leave-rejoin-owner")
    member = create_account(client, label="leave-rejoin-member")
    household_id = create_household(
        client,
        owner=owner,
        name="Leave Rejoin Family",
    )
    first_invitation = create_invitation(
        client,
        owner=owner,
        household_id=household_id,
    )
    join_household(
        client,
        account=member,
        invitation_code=first_invitation["code"],
    )

    leave_response = client.delete(
        f"/api/v1/households/{household_id}/members/me",
        headers=member.headers,
    )
    assert leave_response.status_code == 204
    assert (
        client.get(
            f"/api/v1/households/{household_id}",
            headers=member.headers,
        ).status_code
        == 404
    )
    reused_response = client.post(
        "/api/v1/households/join",
        headers=member.headers,
        json={"invitation_code": first_invitation["code"]},
    )
    assert reused_response.status_code == 400

    new_invitation = create_invitation(
        client,
        owner=owner,
        household_id=household_id,
    )
    join_household(
        client,
        account=member,
        invitation_code=new_invitation["code"],
    )
    restored_response = client.get(
        f"/api/v1/households/{household_id}",
        headers=member.headers,
    )
    member_list_response = client.get(
        f"/api/v1/households/{household_id}/members",
        headers=member.headers,
    )
    assert restored_response.status_code == 200
    assert restored_response.json()["role"] == "member"
    assert len(member_list_response.json()) == 2


def test_removed_member_needs_fresh_non_revoked_invitation(
    client: TestClient,
) -> None:
    owner = create_account(client, label="removed-rejoin-owner")
    member = create_account(client, label="removed-rejoin-member")
    household_id = create_household(
        client,
        owner=owner,
        name="Removed Member Rejoin Family",
    )
    consumed_invitation = create_invitation(
        client,
        owner=owner,
        household_id=household_id,
    )
    join_household(
        client,
        account=member,
        invitation_code=consumed_invitation["code"],
    )

    remove_response = client.delete(
        f"/api/v1/households/{household_id}/members/{member.id}",
        headers=owner.headers,
    )
    assert remove_response.status_code == 204
    consumed_retry = client.post(
        "/api/v1/households/join",
        headers=member.headers,
        json={"invitation_code": consumed_invitation["code"]},
    )
    assert consumed_retry.status_code == 400

    revoked_invitation = create_invitation(
        client,
        owner=owner,
        household_id=household_id,
    )
    revoke_response = client.delete(
        f"/api/v1/households/{household_id}/invitations/{revoked_invitation['id']}",
        headers=owner.headers,
    )
    assert revoke_response.status_code == 204
    revoked_retry = client.post(
        "/api/v1/households/join",
        headers=member.headers,
        json={"invitation_code": revoked_invitation["code"]},
    )
    assert revoked_retry.status_code == 400

    fresh_invitation = create_invitation(
        client,
        owner=owner,
        household_id=household_id,
    )
    join_household(
        client,
        account=member,
        invitation_code=fresh_invitation["code"],
    )
    members_response = client.get(
        f"/api/v1/households/{household_id}/members",
        headers=owner.headers,
    )
    assert members_response.status_code == 200
    assert member.id in {item["user_id"] for item in members_response.json()}
