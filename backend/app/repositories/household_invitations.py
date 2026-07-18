from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.household_invitation import HouseholdInvitation


class HouseholdInvitationRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        household_id: UUID,
        created_by_user_id: UUID,
        code_hash: str,
        expires_at: datetime,
    ) -> HouseholdInvitation:
        invitation = HouseholdInvitation(
            household_id=household_id,
            created_by_user_id=created_by_user_id,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        self.db.add(invitation)
        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def get_active_by_code_hash(
        self,
        code_hash: str,
        *,
        now: datetime | None = None,
    ) -> HouseholdInvitation | None:
        effective_now = now or datetime.now(UTC)
        statement = select(HouseholdInvitation).where(
            HouseholdInvitation.code_hash == code_hash,
            HouseholdInvitation.expires_at > effective_now,
            HouseholdInvitation.used_at.is_(None),
            HouseholdInvitation.revoked_at.is_(None),
        )
        return self.db.execute(statement).scalar_one_or_none()

    def mark_used(
        self,
        invitation: HouseholdInvitation,
        *,
        used_by_user_id: UUID,
        used_at: datetime | None = None,
    ) -> HouseholdInvitation:
        effective_used_at = used_at or datetime.now(UTC)
        result = self.db.execute(
            update(HouseholdInvitation)
            .where(
                HouseholdInvitation.id == invitation.id,
                HouseholdInvitation.expires_at > effective_used_at,
                HouseholdInvitation.used_at.is_(None),
                HouseholdInvitation.revoked_at.is_(None),
            )
            .values(
                used_at=effective_used_at,
                used_by_user_id=used_by_user_id,
            ),
            execution_options={"synchronize_session": False},
        )
        if getattr(result, "rowcount", 0) != 1:
            self.db.rollback()
            raise HouseholdInvitationNotActiveError

        self.db.commit()
        self.db.refresh(invitation)
        return invitation

    def revoke(
        self,
        invitation: HouseholdInvitation,
        *,
        revoked_at: datetime | None = None,
    ) -> HouseholdInvitation:
        effective_revoked_at = revoked_at or datetime.now(UTC)
        result = self.db.execute(
            update(HouseholdInvitation)
            .where(
                HouseholdInvitation.id == invitation.id,
                HouseholdInvitation.expires_at > effective_revoked_at,
                HouseholdInvitation.used_at.is_(None),
                HouseholdInvitation.revoked_at.is_(None),
            )
            .values(revoked_at=effective_revoked_at),
            execution_options={"synchronize_session": False},
        )
        if getattr(result, "rowcount", 0) != 1:
            self.db.rollback()
            raise HouseholdInvitationNotActiveError

        self.db.commit()
        self.db.refresh(invitation)
        return invitation


class HouseholdInvitationNotActiveError(ValueError):
    pass
