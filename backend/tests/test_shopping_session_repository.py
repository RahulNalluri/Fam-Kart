from datetime import UTC, datetime, timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models import Household, ShoppingSession, ShoppingSessionStatus, User
from app.repositories.shopping_sessions import ShoppingSessionRepository


def create_test_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_user(db: Session, *, email: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name="Shopping Session Test",
        password_hash="!",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    return user


def create_household(db: Session, *, name: str) -> Household:
    household = Household(name=name)
    db.add(household)
    db.commit()
    return household


def test_repository_creates_and_finds_active_session() -> None:
    db = create_test_session()
    try:
        user = create_user(db, email="session-creator@example.com")
        household = create_household(db, name="Session Repository Family")
        repository = ShoppingSessionRepository(db)

        created = repository.create(
            household_id=household.id,
            created_by_user_id=user.id,
        )

        active = repository.get_active_for_household(household.id)
        assert active is not None
        assert active.id == created.id
        assert active.household_id == household.id
        assert active.created_by_user_id == user.id
        assert active.status == ShoppingSessionStatus.ACTIVE
        assert active.completed_at is None
    finally:
        db.close()


def test_repository_scopes_session_lookup_to_household() -> None:
    db = create_test_session()
    try:
        user = create_user(db, email="session-scope@example.com")
        household = create_household(db, name="Session Scope Family")
        other_household = create_household(db, name="Other Session Family")
        repository = ShoppingSessionRepository(db)
        created = repository.create(
            household_id=household.id,
            created_by_user_id=user.id,
        )

        assert (
            repository.get_for_household(
                session_id=created.id,
                household_id=household.id,
            )
            is not None
        )
        assert (
            repository.get_for_household(
                session_id=created.id,
                household_id=other_household.id,
            )
            is None
        )
    finally:
        db.close()


def test_repository_lists_only_one_households_sessions_newest_first() -> None:
    db = create_test_session()
    try:
        user = create_user(db, email="session-list@example.com")
        household = create_household(db, name="Session List Family")
        other_household = create_household(db, name="Hidden Session Family")
        now = datetime.now(UTC)
        older = ShoppingSession(
            household_id=household.id,
            created_by_user_id=user.id,
            status=ShoppingSessionStatus.COMPLETED,
            created_at=now - timedelta(days=1),
            completed_at=now,
        )
        newer = ShoppingSession(
            household_id=household.id,
            created_by_user_id=user.id,
            status=ShoppingSessionStatus.ACTIVE,
            created_at=now,
        )
        hidden = ShoppingSession(
            household_id=other_household.id,
            created_by_user_id=user.id,
            status=ShoppingSessionStatus.ACTIVE,
            created_at=now + timedelta(days=1),
        )
        db.add_all([older, newer, hidden])
        db.commit()
        repository = ShoppingSessionRepository(db)

        sessions = repository.list_for_household(household.id)

        assert [session.id for session in sessions] == [newer.id, older.id]
        assert repository.get_active_for_household(household.id) == newer
    finally:
        db.close()


def test_repository_locks_only_an_existing_household() -> None:
    db = create_test_session()
    try:
        household = create_household(db, name="Session Lock Family")
        repository = ShoppingSessionRepository(db)

        assert repository.lock_household(household.id) is True
        assert repository.lock_household(uuid4()) is False
    finally:
        db.close()


def test_repository_rolls_back_when_creation_commit_fails() -> None:
    db = Mock(spec=Session)
    db.commit.side_effect = RuntimeError("database unavailable")
    repository = ShoppingSessionRepository(db)

    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.create(
            household_id=uuid4(),
            created_by_user_id=uuid4(),
        )

    db.rollback.assert_called_once_with()
    db.refresh.assert_not_called()


def test_repository_completes_active_session() -> None:
    db = create_test_session()
    try:
        user = create_user(db, email="session-complete@example.com")
        household = create_household(db, name="Session Completion Family")
        repository = ShoppingSessionRepository(db)
        shopping_session = repository.create(
            household_id=household.id,
            created_by_user_id=user.id,
        )
        completed_at = datetime.now(UTC).replace(microsecond=0)

        completed = repository.complete(
            shopping_session,
            completed_at=completed_at,
        )

        assert completed.status == ShoppingSessionStatus.COMPLETED
        assert completed.completed_at is not None
        assert completed.completed_at.replace(tzinfo=UTC) == completed_at
        assert repository.get_active_for_household(household.id) is None
    finally:
        db.close()


def test_repository_completion_is_idempotent() -> None:
    db = create_test_session()
    try:
        user = create_user(db, email="session-idempotent@example.com")
        household = create_household(db, name="Idempotent Completion Family")
        repository = ShoppingSessionRepository(db)
        shopping_session = repository.create(
            household_id=household.id,
            created_by_user_id=user.id,
        )
        original_completed_at = datetime.now(UTC).replace(microsecond=0)
        first = repository.complete(
            shopping_session,
            completed_at=original_completed_at,
        )

        repeated = repository.complete(
            first,
            completed_at=original_completed_at + timedelta(minutes=5),
        )

        assert repeated.status == ShoppingSessionStatus.COMPLETED
        assert repeated.completed_at is not None
        assert repeated.completed_at.replace(tzinfo=UTC) == original_completed_at
    finally:
        db.close()


def test_repository_rolls_back_when_completion_update_fails() -> None:
    db = Mock(spec=Session)
    db.execute.side_effect = RuntimeError("database unavailable")
    repository = ShoppingSessionRepository(db)
    shopping_session = ShoppingSession(id=uuid4())

    with pytest.raises(RuntimeError, match="database unavailable"):
        repository.complete(shopping_session)

    db.rollback.assert_called_once_with()
    db.commit.assert_not_called()
