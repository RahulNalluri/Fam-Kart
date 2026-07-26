from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
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
    GroceryItem,
    GroceryItemStatus,
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
        display_name="Grocery API User",
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


def create_shopping_session(
    db_session: Session,
    *,
    household: Household,
    creator: User,
    status: ShoppingSessionStatus = ShoppingSessionStatus.ACTIVE,
) -> ShoppingSession:
    shopping_session = ShoppingSession(
        household_id=household.id,
        created_by_user_id=creator.id,
        status=status,
        completed_at=(
            datetime.now(UTC) if status == ShoppingSessionStatus.COMPLETED else None
        ),
    )
    db_session.add(shopping_session)
    db_session.commit()
    db_session.refresh(shopping_session)
    return shopping_session


def authorization_header(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token(user.id)}"}


def collection_url(household_id: object, session_id: object) -> str:
    return f"/api/v1/households/{household_id}/shopping-sessions/{session_id}/items"


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (HouseholdRole.OWNER, "grocery-api-owner@example.com"),
        (HouseholdRole.MEMBER, "grocery-api-member@example.com"),
    ],
)
def test_current_member_can_add_multilingual_grocery_item(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
    email: str,
) -> None:
    user = create_user(db_session, email=email)
    household = create_household(db_session, name="Grocery API Family")
    add_membership(db_session, household=household, user=user, role=role)
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=user,
    )

    response = client.post(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(user),
        json={
            "name": "  Tomatoes - టమాటాలు  ",
            "quantity": "2.500",
            "unit": " kg ",
            "notes": " Ripe ",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["shopping_session_id"] == str(shopping_session.id)
    assert payload["name"] == "Tomatoes - టమాటాలు"
    assert Decimal(payload["quantity"]) == Decimal("2.500")
    assert payload["unit"] == "kg"
    assert payload["notes"] == "Ripe"
    assert payload["status"] == "pending"
    assert payload["created_by_user_id"] == str(user.id)
    assert payload["assigned_to_user_id"] is None
    assert payload["completed_by_user_id"] is None
    assert payload["completed_at"] is None
    assert "email" not in payload
    assert "password_hash" not in payload


def test_member_can_assign_item_to_current_household_member(
    client: TestClient,
    db_session: Session,
) -> None:
    creator = create_user(db_session, email="grocery-api-assigner@example.com")
    assignee = create_user(db_session, email="grocery-api-assignee@example.com")
    household = create_household(db_session, name="Assignment API Family")
    add_membership(
        db_session,
        household=household,
        user=creator,
        role=HouseholdRole.MEMBER,
    )
    add_membership(
        db_session,
        household=household,
        user=assignee,
        role=HouseholdRole.MEMBER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=creator,
    )

    response = client.post(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(creator),
        json={"name": "Milk", "assigned_to_user_id": str(assignee.id)},
    )

    assert response.status_code == 201
    assert response.json()["assigned_to_user_id"] == str(assignee.id)


def test_item_assignment_rejects_user_outside_household(
    client: TestClient,
    db_session: Session,
) -> None:
    creator = create_user(db_session, email="grocery-api-private-assigner@example.com")
    outsider = create_user(db_session, email="grocery-api-private-assignee@example.com")
    household = create_household(db_session, name="Private Assignment Family")
    add_membership(
        db_session,
        household=household,
        user=creator,
        role=HouseholdRole.OWNER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=creator,
    )

    response = client.post(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(creator),
        json={"name": "Milk", "assigned_to_user_id": str(outsider.id)},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "The selected person is not a member of this household."
    )


def test_completed_session_rejects_new_item(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="grocery-api-completed@example.com")
    household = create_household(db_session, name="Completed Grocery Family")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.OWNER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=user,
        status=ShoppingSessionStatus.COMPLETED,
    )

    response = client.post(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(user),
        json={"name": "Rice"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "You cannot add items because this shopping session is already completed."
    )


def test_outsider_and_cross_household_session_return_same_not_found(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-api-scope-member@example.com")
    outsider = create_user(db_session, email="grocery-api-scope-outsider@example.com")
    household = create_household(db_session, name="Visible Grocery Family")
    other_household = create_household(db_session, name="Other Grocery Family")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    hidden_session = create_shopping_session(
        db_session,
        household=other_household,
        creator=outsider,
    )
    url = collection_url(household.id, hidden_session.id)

    cross_household_response = client.post(
        url,
        headers=authorization_header(member),
        json={"name": "Rice"},
    )
    outsider_response = client.post(
        url,
        headers=authorization_header(outsider),
        json={"name": "Rice"},
    )

    assert cross_household_response.status_code == 404
    assert outsider_response.status_code == 404
    assert cross_household_response.json()["error"]["message"] == (
        "This shopping session could not be found or you do not have access to it."
    )
    assert outsider_response.json()["error"]["message"] == (
        "This shopping session could not be found or you do not have access to it."
    )


@pytest.mark.parametrize(
    "session_status",
    [ShoppingSessionStatus.ACTIVE, ShoppingSessionStatus.COMPLETED],
)
def test_member_can_list_items_from_active_or_completed_session(
    client: TestClient,
    db_session: Session,
    session_status: ShoppingSessionStatus,
) -> None:
    member = create_user(
        db_session,
        email=f"grocery-api-list-{session_status.value}@example.com",
    )
    household = create_household(
        db_session,
        name=f"Grocery List {session_status.value}",
    )
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=member,
        status=session_status,
    )
    now = datetime.now(UTC)
    pending = GroceryItem(
        shopping_session_id=shopping_session.id,
        name="Milk",
        status=GroceryItemStatus.PENDING,
        created_by_user_id=member.id,
        created_at=now,
    )
    completed = GroceryItem(
        shopping_session_id=shopping_session.id,
        name="Rice",
        status=GroceryItemStatus.COMPLETED,
        created_by_user_id=member.id,
        created_at=now - timedelta(minutes=1),
        completed_at=now,
    )
    db_session.add_all([completed, pending])
    db_session.commit()

    response = client.get(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(member),
    )

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        str(pending.id),
        str(completed.id),
    ]
    assert [item["status"] for item in response.json()] == [
        "pending",
        "completed",
    ]


def test_outsider_cannot_list_session_items(
    client: TestClient,
    db_session: Session,
) -> None:
    outsider = create_user(db_session, email="grocery-api-list-outsider@example.com")
    household = create_household(db_session, name="Hidden Grocery List")
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=outsider,
    )

    response = client.get(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(outsider),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "This shopping session could not be found or you do not have access to it."
    )


@pytest.mark.parametrize("method", ["POST", "GET"])
def test_grocery_item_endpoints_require_access_token(
    client: TestClient,
    method: str,
) -> None:
    response = client.request(
        method,
        collection_url(uuid4(), uuid4()),
        json={"name": "Rice"} if method == "POST" else None,
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["error"]["message"] == "Please log in again to continue."


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "   "},
        {"name": "Rice", "quantity": 0},
        {"name": "Rice", "quantity": True},
        {"name": "Rice", "quantity": "1.0001"},
        {"name": "Rice", "unknown": "value"},
    ],
)
def test_add_item_rejects_invalid_input(
    client: TestClient,
    db_session: Session,
    payload: dict[str, object],
) -> None:
    member = create_user(db_session, email=f"invalid-item-{uuid4()}@example.com")
    household = create_household(db_session, name=f"Invalid Item {uuid4()}")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.MEMBER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=member,
    )

    response = client.post(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(member),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    "url",
    [
        collection_url("not-a-uuid", uuid4()),
        collection_url(uuid4(), "not-a-uuid"),
    ],
)
def test_grocery_item_endpoints_reject_malformed_ids(
    client: TestClient,
    db_session: Session,
    url: str,
) -> None:
    user = create_user(db_session, email=f"malformed-item-{uuid4()}@example.com")

    response = client.get(url, headers=authorization_header(user))

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
