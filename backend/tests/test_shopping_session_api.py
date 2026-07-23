from collections.abc import Generator
from datetime import UTC, datetime, timedelta
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
from app.models import (
    Household,
    HouseholdMember,
    HouseholdRole,
    ShoppingSession,
    ShoppingSessionStatus,
    User,
)


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


def create_user(db_session: Session, *, email: str) -> User:
    user = User(
        email=email,
        display_name="Shopping API User",
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
) -> None:
    db_session.add(
        HouseholdMember(
            household_id=household.id,
            user_id=user.id,
            role=role,
        ),
    )
    db_session.commit()


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (HouseholdRole.OWNER, "session-api-owner@example.com"),
        (HouseholdRole.MEMBER, "session-api-member@example.com"),
    ],
)
def test_current_household_member_can_create_active_session(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
    email: str,
) -> None:
    user = create_user(db_session, email=email)
    household = create_household(db_session, name="Shopping API Family")
    add_membership(db_session, household=household, user=user, role=role)

    response = client.post(
        f"/api/v1/households/{household.id}/shopping-sessions",
        headers=authorization_header(user),
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["household_id"] == str(household.id)
    assert payload["created_by_user_id"] == str(user.id)
    assert payload["status"] == "active"
    assert payload["completed_at"] is None
    assert "id" in payload
    assert "created_at" in payload
    assert "password_hash" not in payload
    assert "email" not in payload


def test_second_active_session_returns_conflict(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="session-api-conflict@example.com")
    household = create_household(db_session, name="Conflict Family")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.OWNER,
    )
    url = f"/api/v1/households/{household.id}/shopping-sessions"
    headers = authorization_header(user)

    assert client.post(url, headers=headers).status_code == 201
    response = client.post(url, headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "An active shopping session already exists."
    )


def test_outsider_and_unknown_household_return_same_creation_error(
    client: TestClient,
    db_session: Session,
) -> None:
    outsider = create_user(db_session, email="session-api-outsider@example.com")
    household = create_household(db_session, name="Private Session Family")
    headers = authorization_header(outsider)

    outsider_response = client.post(
        f"/api/v1/households/{household.id}/shopping-sessions",
        headers=headers,
    )
    unknown_response = client.post(
        f"/api/v1/households/{uuid4()}/shopping-sessions",
        headers=headers,
    )

    assert outsider_response.status_code == 404
    assert unknown_response.status_code == 404
    assert outsider_response.json()["error"]["message"] == "Household not found."
    assert unknown_response.json()["error"]["message"] == "Household not found."


def test_member_lists_only_households_sessions_newest_first(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="session-api-list@example.com")
    household = create_household(db_session, name="Session List API Family")
    other_household = create_household(db_session, name="Hidden API Family")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    now = datetime.now(UTC)
    older = ShoppingSession(
        household_id=household.id,
        created_by_user_id=member.id,
        status=ShoppingSessionStatus.COMPLETED,
        created_at=now - timedelta(days=1),
        completed_at=now,
    )
    newer = ShoppingSession(
        household_id=household.id,
        created_by_user_id=member.id,
        status=ShoppingSessionStatus.ACTIVE,
        created_at=now,
    )
    hidden = ShoppingSession(
        household_id=other_household.id,
        created_by_user_id=member.id,
        status=ShoppingSessionStatus.ACTIVE,
        created_at=now + timedelta(days=1),
    )
    db_session.add_all([older, newer, hidden])
    db_session.commit()

    response = client.get(
        f"/api/v1/households/{household.id}/shopping-sessions",
        headers=authorization_header(member),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        str(newer.id),
        str(older.id),
    ]
    assert all(item["household_id"] == str(household.id) for item in response.json())


def test_outsider_cannot_list_household_sessions(
    client: TestClient,
    db_session: Session,
) -> None:
    outsider = create_user(db_session, email="session-api-list-outsider@example.com")
    household = create_household(db_session, name="Hidden List Family")

    response = client.get(
        f"/api/v1/households/{household.id}/shopping-sessions",
        headers=authorization_header(outsider),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == "Household not found."


def test_member_can_retrieve_household_session(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="session-api-detail@example.com")
    household = create_household(db_session, name="Session Detail Family")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    shopping_session = ShoppingSession(
        household_id=household.id,
        created_by_user_id=member.id,
        status=ShoppingSessionStatus.ACTIVE,
    )
    db_session.add(shopping_session)
    db_session.commit()

    response = client.get(
        f"/api/v1/households/{household.id}/shopping-sessions/{shopping_session.id}",
        headers=authorization_header(member),
    )

    assert response.status_code == 200
    assert response.json()["id"] == str(shopping_session.id)
    assert response.json()["household_id"] == str(household.id)


def test_cross_household_and_unknown_session_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="session-api-cross-scope@example.com")
    household = create_household(db_session, name="Visible Session Family")
    other_household = create_household(db_session, name="Other Session Family")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    hidden = ShoppingSession(
        household_id=other_household.id,
        created_by_user_id=member.id,
        status=ShoppingSessionStatus.ACTIVE,
    )
    db_session.add(hidden)
    db_session.commit()
    headers = authorization_header(member)

    cross_household_response = client.get(
        f"/api/v1/households/{household.id}/shopping-sessions/{hidden.id}",
        headers=headers,
    )
    unknown_response = client.get(
        f"/api/v1/households/{household.id}/shopping-sessions/{uuid4()}",
        headers=headers,
    )

    assert cross_household_response.status_code == 404
    assert unknown_response.status_code == 404
    assert cross_household_response.json()["error"]["message"] == (
        "Shopping session not found."
    )
    assert unknown_response.json()["error"]["message"] == (
        "Shopping session not found."
    )


@pytest.mark.parametrize(
    ("method", "suffix"),
    [
        ("POST", ""),
        ("GET", ""),
        ("GET", f"/{uuid4()}"),
    ],
)
def test_shopping_session_endpoints_require_access_token(
    client: TestClient,
    method: str,
    suffix: str,
) -> None:
    response = client.request(
        method,
        f"/api/v1/households/{uuid4()}/shopping-sessions{suffix}",
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


@pytest.mark.parametrize(
    "url",
    [
        "/api/v1/households/not-a-uuid/shopping-sessions",
        f"/api/v1/households/{uuid4()}/shopping-sessions/not-a-uuid",
    ],
)
def test_shopping_session_endpoints_reject_malformed_ids(
    client: TestClient,
    db_session: Session,
    url: str,
) -> None:
    user = create_user(db_session, email=f"malformed-{uuid4()}@example.com")

    response = client.get(url, headers=authorization_header(user))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (HouseholdRole.OWNER, "session-complete-owner@example.com"),
        (HouseholdRole.MEMBER, "session-complete-member@example.com"),
    ],
)
def test_current_member_can_complete_session_idempotently(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
    email: str,
) -> None:
    user = create_user(db_session, email=email)
    household = create_household(db_session, name="Completion API Family")
    add_membership(db_session, household=household, user=user, role=role)
    create_response = client.post(
        f"/api/v1/households/{household.id}/shopping-sessions",
        headers=authorization_header(user),
    )
    session_id = create_response.json()["id"]
    url = (
        f"/api/v1/households/{household.id}/shopping-sessions/" f"{session_id}/complete"
    )

    first_response = client.patch(url, headers=authorization_header(user))
    repeated_response = client.patch(url, headers=authorization_header(user))

    assert first_response.status_code == 200
    assert first_response.json()["status"] == "completed"
    assert first_response.json()["completed_at"] is not None
    assert repeated_response.status_code == 200
    assert (
        repeated_response.json()["completed_at"]
        == first_response.json()["completed_at"]
    )


def test_new_session_can_be_created_after_completion(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="session-complete-next@example.com")
    household = create_household(db_session, name="Next Session Family")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.OWNER,
    )
    collection_url = f"/api/v1/households/{household.id}/shopping-sessions"
    headers = authorization_header(user)
    first = client.post(collection_url, headers=headers)
    complete_url = f"{collection_url}/{first.json()['id']}/complete"

    assert client.patch(complete_url, headers=headers).status_code == 200
    second = client.post(collection_url, headers=headers)

    assert second.status_code == 201
    assert second.json()["id"] != first.json()["id"]
    assert second.json()["status"] == "active"


def test_outsider_and_cross_household_session_cannot_complete(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="session-complete-scope@example.com")
    outsider = create_user(db_session, email="session-complete-outsider@example.com")
    household = create_household(db_session, name="Completion Scope Family")
    other_household = create_household(db_session, name="Other Completion Family")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    hidden_session = ShoppingSession(
        household_id=other_household.id,
        created_by_user_id=outsider.id,
        status=ShoppingSessionStatus.ACTIVE,
    )
    db_session.add(hidden_session)
    db_session.commit()
    url = (
        f"/api/v1/households/{household.id}/shopping-sessions/"
        f"{hidden_session.id}/complete"
    )

    cross_household_response = client.patch(
        url,
        headers=authorization_header(member),
    )
    outsider_response = client.patch(
        url,
        headers=authorization_header(outsider),
    )

    assert cross_household_response.status_code == 404
    assert outsider_response.status_code == 404
    assert cross_household_response.json()["error"]["message"] == (
        "Shopping session not found."
    )
    assert outsider_response.json()["error"]["message"] == (
        "Shopping session not found."
    )


def test_complete_session_requires_access_token(client: TestClient) -> None:
    response = client.patch(
        f"/api/v1/households/{uuid4()}/shopping-sessions/{uuid4()}/complete",
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
