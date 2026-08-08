from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.push_device import PushPlatform
from app.models.user import User
from app.repositories.push_devices import (
    PushDeviceRegistrationConflictError,
    PushDeviceRepository,
)


def create_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_user(db: Session, email: str) -> User:
    user = User(
        email=email,
        display_name="Push Device User",
        password_hash="!",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    return user


def test_registers_and_rotates_token_for_same_installation() -> None:
    db = create_session()
    try:
        user = create_user(db, "push-repository@example.com")
        repository = PushDeviceRepository(db)
        installation_id = uuid4()
        first = repository.register(
            user_id=user.id,
            installation_id=installation_id,
            expo_push_token="ExponentPushToken[first_token_123456]",
            platform=PushPlatform.ANDROID,
        )

        updated = repository.register(
            user_id=user.id,
            installation_id=installation_id,
            expo_push_token="ExponentPushToken[rotated_token_1234]",
            platform=PushPlatform.ANDROID,
        )

        assert updated.id == first.id
        assert updated.expo_push_token == "ExponentPushToken[rotated_token_1234]"
        assert updated.is_active is True
    finally:
        db.close()


def test_deactivation_is_scoped_and_idempotent() -> None:
    db = create_session()
    try:
        user = create_user(db, "push-deactivate@example.com")
        other_user = create_user(db, "push-other@example.com")
        repository = PushDeviceRepository(db)
        installation_id = uuid4()
        device = repository.register(
            user_id=user.id,
            installation_id=installation_id,
            expo_push_token="ExpoPushToken[deactivate_token_123]",
            platform=PushPlatform.IOS,
        )
        deactivated_at = datetime.now(UTC)

        assert (
            repository.deactivate_for_user(
                user_id=other_user.id,
                installation_id=installation_id,
                deactivated_at=deactivated_at,
            )
            is False
        )
        assert (
            repository.deactivate_for_user(
                user_id=user.id,
                installation_id=installation_id,
                deactivated_at=deactivated_at,
            )
            is True
        )
        assert device.is_active is False
        assert device.deactivated_at == deactivated_at.replace(tzinfo=None)
        assert (
            repository.deactivate_for_user(
                user_id=user.id,
                installation_id=installation_id,
            )
            is False
        )
    finally:
        db.close()


def test_active_installation_rejects_different_account_and_token() -> None:
    db = create_session()
    try:
        owner = create_user(db, "push-owner@example.com")
        attacker = create_user(db, "push-attacker@example.com")
        repository = PushDeviceRepository(db)
        installation_id = uuid4()
        repository.register(
            user_id=owner.id,
            installation_id=installation_id,
            expo_push_token="ExpoPushToken[owner_token_123456]",
            platform=PushPlatform.ANDROID,
        )

        with pytest.raises(PushDeviceRegistrationConflictError):
            repository.register(
                user_id=attacker.id,
                installation_id=installation_id,
                expo_push_token="ExpoPushToken[attacker_token_123]",
                platform=PushPlatform.ANDROID,
            )
    finally:
        db.close()


def test_deactivated_installation_can_move_to_another_account() -> None:
    db = create_session()
    try:
        first_user = create_user(db, "push-first@example.com")
        second_user = create_user(db, "push-second@example.com")
        repository = PushDeviceRepository(db)
        installation_id = uuid4()
        repository.register(
            user_id=first_user.id,
            installation_id=installation_id,
            expo_push_token="ExpoPushToken[first_user_token_12]",
            platform=PushPlatform.ANDROID,
        )
        repository.deactivate_for_user(
            user_id=first_user.id,
            installation_id=installation_id,
        )

        moved = repository.register(
            user_id=second_user.id,
            installation_id=installation_id,
            expo_push_token="ExpoPushToken[second_user_token_1]",
            platform=PushPlatform.IOS,
        )

        assert moved.user_id == second_user.id
        assert moved.platform is PushPlatform.IOS
        assert moved.is_active is True
        assert moved.deactivated_at is None
    finally:
        db.close()


def test_token_rotation_releases_an_inactive_stale_registration() -> None:
    db = create_session()
    try:
        user = create_user(db, "push-stale-token@example.com")
        repository = PushDeviceRepository(db)
        stale_installation_id = uuid4()
        current_installation_id = uuid4()
        stale_token = "ExpoPushToken[stale_shared_token_123]"
        repository.register(
            user_id=user.id,
            installation_id=stale_installation_id,
            expo_push_token=stale_token,
            platform=PushPlatform.ANDROID,
        )
        repository.deactivate_for_user(
            user_id=user.id,
            installation_id=stale_installation_id,
        )
        current = repository.register(
            user_id=user.id,
            installation_id=current_installation_id,
            expo_push_token="ExpoPushToken[current_token_123456]",
            platform=PushPlatform.ANDROID,
        )

        rotated = repository.register(
            user_id=user.id,
            installation_id=current_installation_id,
            expo_push_token=stale_token,
            platform=PushPlatform.ANDROID,
        )

        assert rotated.id == current.id
        assert repository.get_by_expo_push_token(stale_token) is rotated
        assert repository.get_by_installation_id(stale_installation_id) is None
    finally:
        db.close()
