from collections.abc import Generator
from datetime import datetime, timedelta
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
from app.models import GroceryActivityEvent, GroceryItem, HouseholdRole
from tests.test_grocery_item_api import (
    add_membership,
    authorization_header,
    collection_url,
    create_household,
    create_shopping_session,
    create_user,
    item_url,
)

VERSION_HEADER = "X-Base-Updated-At"
VERSION_CONFLICT_MESSAGE = (
    "This grocery item was changed by another household member. Refresh the list "
    "and review your change."
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


def create_versioned_item(
    client: TestClient,
    db_session: Session,
    *,
    email: str,
) -> tuple[dict[str, str], str, dict[str, object]]:
    user = create_user(db_session, email=email)
    household = create_household(db_session, name=f"Versioned {email}")
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
    headers = authorization_header(user)
    created = client.post(
        collection_url(household.id, shopping_session.id),
        headers=headers,
        json={"name": "Rice", "quantity": "5.000", "unit": "kg"},
    )
    assert created.status_code == 201
    item = created.json()
    return (
        headers,
        item_url(household.id, shopping_session.id, item["id"]),
        item,
    )


def with_version(headers: dict[str, str], item: dict[str, object]) -> dict[str, str]:
    return {**headers, VERSION_HEADER: cast(str, item["updated_at"])}


def test_matching_versions_allow_the_complete_mutation_workflow(
    client: TestClient,
    db_session: Session,
) -> None:
    headers, url, item = create_versioned_item(
        client,
        db_session,
        email="matching-version@example.com",
    )

    edited = client.patch(
        url,
        headers=with_version(headers, item),
        json={"name": "Brown rice"},
    )
    assert edited.status_code == 200

    completed = client.patch(
        f"{url}/complete",
        headers=with_version(headers, edited.json()),
    )
    assert completed.status_code == 200

    reopened = client.patch(
        f"{url}/reopen",
        headers=with_version(headers, completed.json()),
    )
    assert reopened.status_code == 200

    deleted = client.delete(url, headers=with_version(headers, reopened.json()))
    assert deleted.status_code == 204


@pytest.mark.parametrize("action", ["edit", "complete", "reopen", "delete"])
def test_stale_versions_do_not_change_items_or_create_side_effects(
    client: TestClient,
    db_session: Session,
    redis_client: Redis,
    action: str,
) -> None:
    headers, url, item = create_versioned_item(
        client,
        db_session,
        email=f"stale-{action}@example.com",
    )
    if action == "reopen":
        completed = client.patch(f"{url}/complete", headers=headers)
        assert completed.status_code == 200
        item = completed.json()

    stale_version = cast(str, item["updated_at"])
    stored_item = db_session.get(GroceryItem, UUID(cast(str, item["id"])))
    assert stored_item is not None
    stored_item.updated_at = datetime.fromisoformat(stale_version) + timedelta(
        minutes=1
    )
    db_session.commit()
    activity_count = db_session.scalar(
        select(func.count()).select_from(GroceryActivityEvent),
    )
    publish_count = cast(AsyncMock, redis_client.publish).await_count
    stale_headers = {**headers, VERSION_HEADER: stale_version}

    if action == "edit":
        response = client.patch(
            url,
            headers=stale_headers,
            json={"name": "Stale brown rice"},
        )
    elif action == "delete":
        response = client.delete(url, headers=stale_headers)
    else:
        response = client.patch(f"{url}/{action}", headers=stale_headers)

    assert response.status_code == 412
    assert response.json()["error"]["message"] == VERSION_CONFLICT_MESSAGE
    assert db_session.get(GroceryItem, UUID(cast(str, item["id"]))) is not None
    assert (
        db_session.scalar(select(func.count()).select_from(GroceryActivityEvent))
        == activity_count
    )
    assert cast(AsyncMock, redis_client.publish).await_count == publish_count


def test_invalid_version_header_is_rejected_before_mutation(
    client: TestClient,
    db_session: Session,
) -> None:
    headers, url, item = create_versioned_item(
        client,
        db_session,
        email="invalid-version@example.com",
    )

    response = client.patch(
        url,
        headers={**headers, VERSION_HEADER: "not-a-timestamp"},
        json={"name": "Blocked edit"},
    )

    assert response.status_code == 422
    stored_item = db_session.get(GroceryItem, UUID(cast(str, item["id"])))
    assert stored_item is not None
    assert stored_item.name == "Rice"


def test_idempotent_retry_replays_before_the_committed_version_is_rechecked(
    client: TestClient,
    db_session: Session,
) -> None:
    headers, url, item = create_versioned_item(
        client,
        db_session,
        email="version-idempotent@example.com",
    )
    mutation_headers = {
        **with_version(headers, item),
        "Idempotency-Key": str(uuid4()),
    }

    first = client.patch(url, headers=mutation_headers, json={"name": "Brown rice"})
    replay = client.patch(url, headers=mutation_headers, json={"name": "Brown rice"})

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert (
        db_session.scalar(select(func.count()).select_from(GroceryActivityEvent)) == 2
    )


def test_idempotency_key_cannot_be_reused_with_a_different_base_version(
    client: TestClient,
    db_session: Session,
) -> None:
    headers, url, item = create_versioned_item(
        client,
        db_session,
        email="version-key-conflict@example.com",
    )
    mutation_id = str(uuid4())
    first = client.patch(
        url,
        headers={**with_version(headers, item), "Idempotency-Key": mutation_id},
        json={"name": "Brown rice"},
    )
    assert first.status_code == 200

    conflict = client.patch(
        url,
        headers={
            **headers,
            VERSION_HEADER: (
                datetime.fromisoformat(cast(str, item["updated_at"]))
                + timedelta(minutes=1)
            ).isoformat(),
            "Idempotency-Key": mutation_id,
        },
        json={"name": "Brown rice"},
    )

    assert conflict.status_code == 409
    assert conflict.json()["error"]["message"] == (
        "This idempotency key was already used for a different grocery change."
    )
