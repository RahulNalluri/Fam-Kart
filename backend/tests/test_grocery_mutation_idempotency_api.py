from collections.abc import Generator
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from redis.asyncio import Redis
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.redis import get_redis
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import (
    GroceryActivityEvent,
    GroceryItem,
    GroceryMutationIdempotency,
    User,
)
from app.models.household_member import HouseholdMember, HouseholdRole
from tests.test_grocery_item_api import (
    activity_url,
    add_membership,
    authorization_header,
    collection_url,
    create_household,
    create_shopping_session,
    create_user,
    item_url,
    transition_url,
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
def redis_client() -> Redis:
    client = Mock(spec=Redis)
    client.publish = AsyncMock(return_value=0)
    return client


@pytest.fixture
def client(
    db_session: Session,
    redis_client: Redis,
) -> Generator[TestClient, None, None]:
    def override_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_redis] = lambda: redis_client
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def idempotency_header(user: User, mutation_id: UUID) -> dict[str, str]:
    return {
        **authorization_header(user),
        "Idempotency-Key": str(mutation_id),
    }


def test_all_grocery_mutations_replay_without_duplicate_side_effects(
    client: TestClient,
    db_session: Session,
    redis_client: Redis,
) -> None:
    user = create_user(db_session, email="idempotency-workflow@example.com")
    household = create_household(db_session, name="Idempotent Family")
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
    )

    add_headers = idempotency_header(user, uuid4())
    add_payload = {"name": "Rice", "quantity": "5.000", "unit": "kg"}
    first_add = client.post(
        collection_url(household.id, shopping_session.id),
        headers=add_headers,
        json=add_payload,
    )
    repeated_add = client.post(
        collection_url(household.id, shopping_session.id),
        headers=add_headers,
        json=add_payload,
    )
    assert first_add.status_code == repeated_add.status_code == 201
    assert repeated_add.json() == first_add.json()
    item_id = first_add.json()["id"]

    mutation_requests = [
        (
            "patch",
            item_url(household.id, shopping_session.id, item_id),
            {"name": "Brown Rice"},
        ),
        (
            "patch",
            transition_url(
                household.id,
                shopping_session.id,
                item_id,
                "complete",
            ),
            None,
        ),
        (
            "patch",
            transition_url(
                household.id,
                shopping_session.id,
                item_id,
                "reopen",
            ),
            None,
        ),
    ]
    for method, url, payload in mutation_requests:
        headers = idempotency_header(user, uuid4())
        first = client.request(method, url, headers=headers, json=payload)
        repeated = client.request(method, url, headers=headers, json=payload)
        assert first.status_code == repeated.status_code == 200
        assert repeated.json() == first.json()

    delete_headers = idempotency_header(user, uuid4())
    first_delete = client.delete(
        item_url(household.id, shopping_session.id, item_id),
        headers=delete_headers,
    )
    repeated_delete = client.delete(
        item_url(household.id, shopping_session.id, item_id),
        headers=delete_headers,
    )
    assert first_delete.status_code == repeated_delete.status_code == 204

    assert db_session.scalar(select(func.count()).select_from(GroceryItem)) == 0
    assert (
        db_session.scalar(select(func.count()).select_from(GroceryActivityEvent)) == 5
    )
    assert (
        db_session.scalar(
            select(func.count()).select_from(GroceryMutationIdempotency),
        )
        == 5
    )
    activity = client.get(
        activity_url(household.id, shopping_session.id),
        headers=authorization_header(user),
    )
    assert activity.status_code == 200
    assert len(activity.json()) == 5
    assert cast(AsyncMock, redis_client.publish).await_count == 5


def test_changed_request_with_same_key_returns_understandable_conflict(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="idempotency-conflict@example.com")
    household = create_household(db_session, name="Conflict Family")
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
    )
    headers = idempotency_header(user, uuid4())
    url = collection_url(household.id, shopping_session.id)

    first = client.post(url, headers=headers, json={"name": "Rice"})
    conflict = client.post(url, headers=headers, json={"name": "Milk"})

    assert first.status_code == 201
    assert conflict.status_code == 409
    assert conflict.json()["error"]["message"] == (
        "This idempotency key was already used for a different grocery change."
    )
    assert db_session.scalar(select(func.count()).select_from(GroceryItem)) == 1
    assert (
        db_session.scalar(select(func.count()).select_from(GroceryActivityEvent)) == 1
    )


def test_invalid_idempotency_key_is_rejected_before_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="idempotency-invalid@example.com")
    household = create_household(db_session, name="Invalid Key Family")
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
    )

    response = client.post(
        collection_url(household.id, shopping_session.id),
        headers={
            **authorization_header(user),
            "Idempotency-Key": "not-a-uuid",
        },
        json={"name": "Rice"},
    )

    assert response.status_code == 422
    assert db_session.scalar(select(func.count()).select_from(GroceryItem)) == 0


def test_replay_rechecks_current_household_membership(
    client: TestClient,
    db_session: Session,
) -> None:
    user = create_user(db_session, email="idempotency-revoked@example.com")
    household = create_household(db_session, name="Revoked Replay Family")
    add_membership(
        db_session,
        household=household,
        user=user,
        role=HouseholdRole.MEMBER,
    )
    shopping_session = create_shopping_session(
        db_session,
        household=household,
        creator=user,
    )
    headers = idempotency_header(user, uuid4())
    url = collection_url(household.id, shopping_session.id)
    first = client.post(url, headers=headers, json={"name": "Rice"})
    assert first.status_code == 201

    membership = db_session.scalar(
        select(HouseholdMember).where(
            HouseholdMember.user_id == user.id,
            HouseholdMember.household_id == household.id,
        ),
    )
    assert membership is not None
    db_session.delete(membership)
    db_session.commit()

    replay = client.post(url, headers=headers, json={"name": "Rice"})

    assert replay.status_code == 404
    assert replay.json()["error"]["message"] == (
        "This shopping session could not be found or you do not have access to it."
    )
