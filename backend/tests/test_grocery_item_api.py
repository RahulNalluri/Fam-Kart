from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

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
    GroceryActivityEvent,
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


def item_url(household_id: object, session_id: object, item_id: object) -> str:
    return f"{collection_url(household_id, session_id)}/{item_id}"


def transition_url(
    household_id: object,
    session_id: object,
    item_id: object,
    action: str,
) -> str:
    return f"{item_url(household_id, session_id, item_id)}/{action}"


def activity_url(household_id: object, session_id: object) -> str:
    return f"{collection_url(household_id, session_id)}/activity"


def create_grocery_item(
    db_session: Session,
    *,
    shopping_session: ShoppingSession,
    creator: User,
    status: GroceryItemStatus = GroceryItemStatus.PENDING,
) -> GroceryItem:
    now = datetime.now(UTC)
    item = GroceryItem(
        shopping_session_id=shopping_session.id,
        name="Rice",
        quantity=Decimal("5.000"),
        unit="kg",
        notes="Original note",
        status=status,
        created_by_user_id=creator.id,
        completed_by_user_id=(
            creator.id if status == GroceryItemStatus.COMPLETED else None
        ),
        completed_at=now if status == GroceryItemStatus.COMPLETED else None,
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item


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


def test_add_item_rejects_normalized_pending_duplicate(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-duplicate-add@example.com")
    household = create_household(db_session, name="Duplicate Grocery Add")
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
    url = collection_url(household.id, shopping_session.id)
    headers = authorization_header(member)

    created = client.post(
        url,
        headers=headers,
        json={"name": "  Brown   Rice  "},
    )
    duplicate = client.post(
        url,
        headers=headers,
        json={"name": "brown rice"},
    )

    assert created.status_code == 201
    assert created.json()["name"] == "Brown Rice"
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["message"] == (
        "This item is already pending in this shopping session."
    )
    assert len(db_session.query(GroceryItem).all()) == 1
    assert len(db_session.query(GroceryActivityEvent).all()) == 1


def test_edit_item_rejects_pending_duplicate_name(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-duplicate-edit@example.com")
    household = create_household(db_session, name="Duplicate Grocery Edit")
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
    rice = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )
    milk_response = client.post(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(member),
        json={"name": "Milk"},
    )
    milk_id = milk_response.json()["id"]

    response = client.patch(
        item_url(household.id, shopping_session.id, milk_id),
        headers=authorization_header(member),
        json={"name": " rIcE "},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "This item is already pending in this shopping session."
    )
    db_session.expire_all()
    persisted_milk = db_session.get(GroceryItem, UUID(milk_id))
    assert persisted_milk is not None
    assert persisted_milk.name == "Milk"
    assert db_session.get(GroceryItem, rice.id) is not None


def test_reopen_item_rejects_pending_duplicate_name(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-duplicate-reopen@example.com")
    household = create_household(db_session, name="Duplicate Grocery Reopen")
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
    completed_rice = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
        status=GroceryItemStatus.COMPLETED,
    )
    replacement = client.post(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(member),
        json={"name": "rice"},
    )

    response = client.patch(
        transition_url(
            household.id,
            shopping_session.id,
            completed_rice.id,
            "reopen",
        ),
        headers=authorization_header(member),
    )

    assert replacement.status_code == 201
    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "This item is already pending in this shopping session."
    )
    db_session.expire_all()
    persisted = db_session.get(GroceryItem, completed_rice.id)
    assert persisted is not None
    assert persisted.status == GroceryItemStatus.COMPLETED


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


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (HouseholdRole.OWNER, "grocery-edit-owner@example.com"),
        (HouseholdRole.MEMBER, "grocery-edit-member@example.com"),
    ],
)
def test_household_member_can_edit_pending_item(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
    email: str,
) -> None:
    editor = create_user(db_session, email=email)
    assignee = create_user(db_session, email=f"assignee-{email}")
    household = create_household(db_session, name=f"Editable {role.value}")
    add_membership(db_session, household=household, user=editor, role=role)
    add_membership(
        db_session,
        household=household,
        user=assignee,
        role=HouseholdRole.MEMBER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=editor,
    )
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=editor,
    )

    response = client.patch(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(editor),
        json={
            "name": "  Brown rice  ",
            "quantity": "2.500",
            "unit": " packet ",
            "notes": " Updated note ",
            "assigned_to_user_id": str(assignee.id),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Brown rice"
    assert Decimal(payload["quantity"]) == Decimal("2.500")
    assert payload["unit"] == "packet"
    assert payload["notes"] == "Updated note"
    assert payload["assigned_to_user_id"] == str(assignee.id)
    assert payload["created_by_user_id"] == str(editor.id)
    assert payload["status"] == "pending"

    db_session.expire_all()
    persisted = db_session.get(GroceryItem, item.id)
    assert persisted is not None
    assert persisted.name == "Brown rice"
    assert persisted.assigned_to_user_id == assignee.id


def test_edit_can_clear_optional_fields_without_changing_name(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-edit-clear@example.com")
    household = create_household(db_session, name="Clear Grocery Fields")
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
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )
    item.assigned_to_user_id = member.id
    db_session.commit()

    response = client.patch(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(member),
        json={
            "quantity": None,
            "unit": None,
            "notes": None,
            "assigned_to_user_id": None,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["name"] == "Rice"
    assert payload["quantity"] is None
    assert payload["unit"] is None
    assert payload["notes"] is None
    assert payload["assigned_to_user_id"] is None


def test_edit_rejects_assignee_outside_household(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-edit-assigner@example.com")
    outsider = create_user(db_session, email="grocery-edit-outsider@example.com")
    household = create_household(db_session, name="Private Grocery Edit")
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
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )

    response = client.patch(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(member),
        json={"assigned_to_user_id": str(outsider.id)},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "The selected person is not a member of this household."
    )


def test_outsider_cannot_edit_or_discover_item(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-edit-private@example.com")
    outsider = create_user(db_session, email="grocery-edit-denied@example.com")
    household = create_household(db_session, name="Hidden Grocery Edit")
    add_membership(
        db_session,
        household=household,
        user=member,
        role=HouseholdRole.OWNER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=member,
    )
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )

    response = client.patch(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(outsider),
        json={"name": "Hidden update"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "This grocery item could not be found or you do not have access to it."
    )


@pytest.mark.parametrize(
    ("session_status", "item_status", "expected_message"),
    [
        (
            ShoppingSessionStatus.COMPLETED,
            GroceryItemStatus.PENDING,
            "You cannot edit items because this shopping session is already completed.",
        ),
        (
            ShoppingSessionStatus.ACTIVE,
            GroceryItemStatus.COMPLETED,
            "Reopen this grocery item before editing it.",
        ),
    ],
)
def test_edit_rejects_completed_session_or_item(
    client: TestClient,
    db_session: Session,
    session_status: ShoppingSessionStatus,
    item_status: GroceryItemStatus,
    expected_message: str,
) -> None:
    member = create_user(
        db_session,
        email=f"grocery-edit-{session_status.value}-{item_status.value}@example.com",
    )
    household = create_household(
        db_session,
        name=f"Locked {session_status.value} {item_status.value}",
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
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
        status=item_status,
    )

    response = client.patch(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(member),
        json={"name": "Blocked edit"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == expected_message


def test_edit_requires_authentication(client: TestClient) -> None:
    response = client.patch(
        item_url(uuid4(), uuid4(), uuid4()),
        json={"name": "Rice"},
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Please log in again to continue."


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": None},
        {"name": "   "},
        {"quantity": 0},
        {"status": "completed"},
    ],
)
def test_edit_rejects_invalid_input(
    client: TestClient,
    db_session: Session,
    payload: dict[str, object],
) -> None:
    member = create_user(
        db_session, email=f"grocery-edit-invalid-{uuid4()}@example.com"
    )
    household = create_household(db_session, name=f"Invalid Grocery Edit {uuid4()}")
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
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )

    response = client.patch(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(member),
        json=payload,
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_household_members_can_complete_and_reopen_item_idempotently(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="grocery-transition-owner@example.com")
    member = create_user(db_session, email="grocery-transition-member@example.com")
    household = create_household(db_session, name="Grocery Transitions")
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
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=owner,
    )
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=owner,
    )
    complete_url = transition_url(
        household.id,
        shopping_session.id,
        item.id,
        "complete",
    )
    reopen_url = transition_url(
        household.id,
        shopping_session.id,
        item.id,
        "reopen",
    )

    completed = client.patch(complete_url, headers=authorization_header(member))
    repeated_complete = client.patch(
        complete_url,
        headers=authorization_header(owner),
    )

    assert completed.status_code == 200
    assert completed.json()["status"] == "completed"
    assert completed.json()["completed_by_user_id"] == str(member.id)
    assert completed.json()["completed_at"] is not None
    assert repeated_complete.status_code == 200
    assert repeated_complete.json()["completed_by_user_id"] == str(member.id)
    assert repeated_complete.json()["completed_at"] == completed.json()["completed_at"]

    reopened = client.patch(reopen_url, headers=authorization_header(owner))
    repeated_reopen = client.patch(
        reopen_url,
        headers=authorization_header(member),
    )

    assert reopened.status_code == 200
    assert reopened.json()["status"] == "pending"
    assert reopened.json()["completed_by_user_id"] is None
    assert reopened.json()["completed_at"] is None
    assert repeated_reopen.status_code == 200
    assert repeated_reopen.json()["status"] == "pending"
    assert repeated_reopen.json()["completed_by_user_id"] is None
    assert repeated_reopen.json()["completed_at"] is None


@pytest.mark.parametrize("action", ["complete", "reopen"])
def test_outsider_cannot_transition_or_discover_item(
    client: TestClient,
    db_session: Session,
    action: str,
) -> None:
    member = create_user(db_session, email=f"transition-member-{action}@example.com")
    outsider = create_user(
        db_session,
        email=f"transition-outsider-{action}@example.com",
    )
    household = create_household(db_session, name=f"Private Transition {action}")
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
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )

    response = client.patch(
        transition_url(household.id, shopping_session.id, item.id, action),
        headers=authorization_header(outsider),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "This grocery item could not be found or you do not have access to it."
    )


@pytest.mark.parametrize(
    ("action", "expected_message"),
    [
        (
            "complete",
            "You cannot complete items because this shopping session is already "
            "completed.",
        ),
        (
            "reopen",
            "You cannot reopen items because this shopping session is already "
            "completed.",
        ),
    ],
)
def test_completed_session_rejects_item_transition(
    client: TestClient,
    db_session: Session,
    action: str,
    expected_message: str,
) -> None:
    member = create_user(db_session, email=f"locked-transition-{action}@example.com")
    household = create_household(db_session, name=f"Locked Transition {action}")
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
        status=ShoppingSessionStatus.COMPLETED,
    )
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )

    response = client.patch(
        transition_url(household.id, shopping_session.id, item.id, action),
        headers=authorization_header(member),
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == expected_message


@pytest.mark.parametrize("action", ["complete", "reopen"])
def test_item_transition_requires_authentication(
    client: TestClient,
    action: str,
) -> None:
    response = client.patch(
        transition_url(uuid4(), uuid4(), uuid4(), action),
    )

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Please log in again to continue."


@pytest.mark.parametrize("action", ["complete", "reopen"])
def test_item_transition_rejects_malformed_item_id(
    client: TestClient,
    db_session: Session,
    action: str,
) -> None:
    member = create_user(
        db_session,
        email=f"malformed-transition-{action}@example.com",
    )

    response = client.patch(
        transition_url(uuid4(), uuid4(), "not-a-uuid", action),
        headers=authorization_header(member),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.parametrize(
    ("role", "email"),
    [
        (HouseholdRole.OWNER, "grocery-delete-owner@example.com"),
        (HouseholdRole.MEMBER, "grocery-delete-member@example.com"),
    ],
)
def test_household_member_can_permanently_delete_pending_item(
    client: TestClient,
    db_session: Session,
    role: HouseholdRole,
    email: str,
) -> None:
    member = create_user(db_session, email=email)
    household = create_household(db_session, name=f"Delete Grocery {role.value}")
    add_membership(db_session, household=household, user=member, role=role)
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=member,
    )
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )
    item_id = item.id

    response = client.delete(
        item_url(household.id, shopping_session.id, item_id),
        headers=authorization_header(member),
    )

    assert response.status_code == 204
    assert response.content == b""
    assert db_session.get(GroceryItem, item_id) is None

    listed = client.get(
        collection_url(household.id, shopping_session.id),
        headers=authorization_header(member),
    )
    assert listed.status_code == 200
    assert listed.json() == []


def test_outsider_cannot_delete_or_discover_item(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-delete-private@example.com")
    outsider = create_user(db_session, email="grocery-delete-outsider@example.com")
    household = create_household(db_session, name="Private Grocery Delete")
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
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )

    response = client.delete(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(outsider),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "This grocery item could not be found or you do not have access to it."
    )
    assert db_session.get(GroceryItem, item.id) is not None


def test_completed_item_must_be_reopened_before_deletion(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-delete-completed@example.com")
    household = create_household(db_session, name="Completed Grocery Delete")
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
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
        status=GroceryItemStatus.COMPLETED,
    )

    response = client.delete(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(member),
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "Reopen this grocery item before deleting it."
    )
    assert db_session.get(GroceryItem, item.id) is not None


def test_completed_session_rejects_item_deletion(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-delete-locked@example.com")
    household = create_household(db_session, name="Locked Grocery Delete")
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
        status=ShoppingSessionStatus.COMPLETED,
    )
    item = create_grocery_item(
        db_session,
        shopping_session=shopping_session,
        creator=member,
    )

    response = client.delete(
        item_url(household.id, shopping_session.id, item.id),
        headers=authorization_header(member),
    )

    assert response.status_code == 409
    assert response.json()["error"]["message"] == (
        "You cannot delete items because this shopping session is already completed."
    )
    assert db_session.get(GroceryItem, item.id) is not None


def test_delete_item_requires_authentication(client: TestClient) -> None:
    response = client.delete(item_url(uuid4(), uuid4(), uuid4()))

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Please log in again to continue."


def test_delete_item_rejects_malformed_item_id(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="grocery-delete-malformed@example.com")

    response = client.delete(
        item_url(uuid4(), uuid4(), "not-a-uuid"),
        headers=authorization_header(member),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_grocery_mutations_create_ordered_activity_without_idempotent_duplicates(
    client: TestClient,
    db_session: Session,
) -> None:
    owner = create_user(db_session, email="activity-api-owner@example.com")
    member = create_user(db_session, email="activity-api-member@example.com")
    household = create_household(db_session, name="Activity API Household")
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
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=owner,
    )
    collection = collection_url(household.id, shopping_session.id)

    created = client.post(
        collection,
        headers=authorization_header(owner),
        json={"name": "Rice"},
    )
    assert created.status_code == 201
    item_id = created.json()["id"]
    item = item_url(household.id, shopping_session.id, item_id)

    edited = client.patch(
        item,
        headers=authorization_header(member),
        json={"name": "Brown rice"},
    )
    completed = client.patch(
        f"{item}/complete",
        headers=authorization_header(owner),
    )
    repeated_complete = client.patch(
        f"{item}/complete",
        headers=authorization_header(member),
    )
    reopened = client.patch(
        f"{item}/reopen",
        headers=authorization_header(member),
    )
    repeated_reopen = client.patch(
        f"{item}/reopen",
        headers=authorization_header(owner),
    )
    deleted = client.delete(item, headers=authorization_header(owner))

    assert edited.status_code == 200
    assert completed.status_code == 200
    assert repeated_complete.status_code == 200
    assert reopened.status_code == 200
    assert repeated_reopen.status_code == 200
    assert deleted.status_code == 204

    response = client.get(
        activity_url(household.id, shopping_session.id),
        headers=authorization_header(member),
    )

    assert response.status_code == 200
    events = response.json()
    assert [event["event_type"] for event in events] == [
        "item_deleted",
        "item_reopened",
        "item_completed",
        "item_edited",
        "item_added",
    ]
    assert [event["actor_user_id"] for event in events] == [
        str(owner.id),
        str(member.id),
        str(owner.id),
        str(member.id),
        str(owner.id),
    ]
    assert [event["item_name"] for event in events] == [
        "Brown rice",
        "Brown rice",
        "Brown rice",
        "Brown rice",
        "Rice",
    ]
    assert {event["grocery_item_id"] for event in events} == {item_id}
    assert [event["sequence_number"] for event in events] == [5, 4, 3, 2, 1]
    assert db_session.get(GroceryItem, UUID(item_id)) is None
    assert db_session.query(GroceryActivityEvent).count() == 5


def test_activity_list_honors_limit(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="activity-limit@example.com")
    household = create_household(db_session, name="Limited Activity")
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
    collection = collection_url(household.id, shopping_session.id)
    headers = authorization_header(member)
    for name in ("Rice", "Milk", "Onions"):
        assert (
            client.post(collection, headers=headers, json={"name": name}).status_code
            == 201
        )

    response = client.get(
        f"{activity_url(household.id, shopping_session.id)}?limit=2",
        headers=headers,
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert [event["item_name"] for event in response.json()] == ["Onions", "Milk"]


def test_outsider_cannot_list_grocery_activity(
    client: TestClient,
    db_session: Session,
) -> None:
    member = create_user(db_session, email="activity-private@example.com")
    outsider = create_user(db_session, email="activity-outsider@example.com")
    household = create_household(db_session, name="Private Activity")
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

    response = client.get(
        activity_url(household.id, shopping_session.id),
        headers=authorization_header(outsider),
    )

    assert response.status_code == 404
    assert response.json()["error"]["message"] == (
        "This shopping session could not be found or you do not have access to it."
    )


def test_activity_list_requires_authentication(client: TestClient) -> None:
    response = client.get(activity_url(uuid4(), uuid4()))

    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Please log in again to continue."


@pytest.mark.parametrize("limit", [0, 101])
def test_activity_list_validates_limit(
    client: TestClient,
    db_session: Session,
    limit: int,
) -> None:
    member = create_user(db_session, email=f"activity-limit-{limit}@example.com")

    response = client.get(
        f"{activity_url(uuid4(), uuid4())}?limit={limit}",
        headers=authorization_header(member),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
