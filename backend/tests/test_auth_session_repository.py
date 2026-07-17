from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.user import User
from app.repositories.auth_sessions import (
    AuthSessionNotActiveError,
    AuthSessionRepository,
)


def create_test_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_user(db: Session) -> User:
    user = User(
        id=uuid4(),
        email="repository@example.com",
        display_name="Repository Test",
        password_hash="!",
        preferred_language="en",
        is_active=True,
    )
    db.add(user)
    db.commit()
    return user


def test_auth_session_repository_create_and_find() -> None:
    db = create_test_session()
    try:
        user = create_user(db)
        repository = AuthSessionRepository(db)
        expires_at = datetime.now(UTC) + timedelta(days=30)
        token_hash = "a" * 64

        created = repository.create(
            user_id=user.id,
            refresh_token_hash=token_hash,
            expires_at=expires_at,
        )
        found = repository.get_by_refresh_token_hash(token_hash)

        assert found is not None
        assert found.id == created.id
        assert found.user_id == user.id
        assert found.refresh_token_hash == token_hash
        assert found.revoked_at is None
    finally:
        db.close()


def test_auth_session_repository_revoke() -> None:
    db = create_test_session()
    try:
        user = create_user(db)
        repository = AuthSessionRepository(db)
        auth_session = repository.create(
            user_id=user.id,
            refresh_token_hash="b" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=30),
        )
        revoked_at = datetime.now(UTC).replace(tzinfo=None)

        revoked = repository.revoke(auth_session, revoked_at=revoked_at)

        assert revoked.revoked_at == revoked_at

        with pytest.raises(AuthSessionNotActiveError):
            repository.revoke(auth_session, revoked_at=revoked_at)
    finally:
        db.close()


def test_auth_session_repository_rotates_only_once() -> None:
    db = create_test_session()
    try:
        user = create_user(db)
        repository = AuthSessionRepository(db)
        now = datetime.now(UTC).replace(tzinfo=None)
        auth_session = repository.create(
            user_id=user.id,
            refresh_token_hash="c" * 64,
            expires_at=now + timedelta(days=30),
        )

        replacement = repository.rotate(
            auth_session,
            new_refresh_token_hash="d" * 64,
            new_expires_at=now + timedelta(days=30),
            rotated_at=now,
        )

        assert replacement.user_id == user.id
        assert replacement.refresh_token_hash == "d" * 64
        assert replacement.revoked_at is None

        with pytest.raises(AuthSessionNotActiveError):
            repository.rotate(
                auth_session,
                new_refresh_token_hash="e" * 64,
                new_expires_at=now + timedelta(days=30),
                rotated_at=now,
            )
    finally:
        db.close()
