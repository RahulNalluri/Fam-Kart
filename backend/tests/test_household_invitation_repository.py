from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core.invitations import hash_invitation_code
from app.db.base import Base
from app.models import Household, User
from app.repositories.household_invitations import (
    HouseholdInvitationNotActiveError,
    HouseholdInvitationRepository,
)


def create_test_session() -> Session:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    return Session(engine)


def create_user(db: Session, *, email: str) -> User:
    user = User(
        id=uuid4(),
        email=email,
        display_name="Invitation Test",
        password_hash="!",
        preferred_language="en",
    )
    db.add(user)
    db.commit()
    return user


def create_household(db: Session) -> Household:
    household = Household(name="Invitation Test Family")
    db.add(household)
    db.commit()
    return household


def test_invitation_repository_creates_and_finds_active_hash() -> None:
    db = create_test_session()
    try:
        creator = create_user(db, email="creator@example.com")
        household = create_household(db)
        repository = HouseholdInvitationRepository(db)
        now = datetime.now().replace(microsecond=0)
        code_hash = hash_invitation_code("FK-ABCD2345WXYZ")

        created = repository.create(
            household_id=household.id,
            created_by_user_id=creator.id,
            code_hash=code_hash,
            expires_at=now + timedelta(hours=24),
        )
        found = repository.get_active_by_code_hash(code_hash, now=now)

        assert found is not None
        assert found.id == created.id
        assert found.household_id == household.id
        assert found.created_by_user_id == creator.id
        assert found.code_hash == code_hash
        assert found.code_hash != "FK-ABCD2345WXYZ"
        assert found.used_at is None
        assert found.revoked_at is None
    finally:
        db.close()


def test_invitation_repository_excludes_expired_invitation() -> None:
    db = create_test_session()
    try:
        creator = create_user(db, email="expired@example.com")
        household = create_household(db)
        repository = HouseholdInvitationRepository(db)
        now = datetime.now().replace(microsecond=0)
        code_hash = hash_invitation_code("FK-EXPR2345WXYZ")
        repository.create(
            household_id=household.id,
            created_by_user_id=creator.id,
            code_hash=code_hash,
            expires_at=now - timedelta(seconds=1),
        )

        assert repository.get_active_by_code_hash(code_hash, now=now) is None
    finally:
        db.close()


def test_invitation_repository_marks_invitation_used_only_once() -> None:
    db = create_test_session()
    try:
        creator = create_user(db, email="used-creator@example.com")
        joining_user = create_user(db, email="joining@example.com")
        household = create_household(db)
        repository = HouseholdInvitationRepository(db)
        now = datetime.now().replace(microsecond=0)
        code_hash = hash_invitation_code("FK-USED2345WXYZ")
        invitation = repository.create(
            household_id=household.id,
            created_by_user_id=creator.id,
            code_hash=code_hash,
            expires_at=now + timedelta(hours=24),
        )

        used = repository.mark_used(
            invitation,
            used_by_user_id=joining_user.id,
            used_at=now,
        )

        assert used.used_at == now
        assert used.used_by_user_id == joining_user.id
        assert repository.get_active_by_code_hash(code_hash, now=now) is None
        with pytest.raises(HouseholdInvitationNotActiveError):
            repository.mark_used(
                invitation,
                used_by_user_id=joining_user.id,
                used_at=now,
            )
    finally:
        db.close()


def test_invitation_repository_revokes_invitation_only_once() -> None:
    db = create_test_session()
    try:
        creator = create_user(db, email="revoked@example.com")
        household = create_household(db)
        repository = HouseholdInvitationRepository(db)
        now = datetime.now().replace(microsecond=0)
        code_hash = hash_invitation_code("FK-REVK2345WXYZ")
        invitation = repository.create(
            household_id=household.id,
            created_by_user_id=creator.id,
            code_hash=code_hash,
            expires_at=now + timedelta(hours=24),
        )

        revoked = repository.revoke(invitation, revoked_at=now)

        assert revoked.revoked_at == now
        assert repository.get_active_by_code_hash(code_hash, now=now) is None
        with pytest.raises(HouseholdInvitationNotActiveError):
            repository.revoke(invitation, revoked_at=now)
    finally:
        db.close()
