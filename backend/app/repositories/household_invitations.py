from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.household_invitation import HouseholdInvitation
from app.models.household_member import HouseholdMember, HouseholdRole


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

    def list_active_for_household(
        self,
        household_id: UUID,
        *,
        now: datetime | None = None,
    ) -> list[HouseholdInvitation]:
        effective_now = now or datetime.now(UTC)
        statement = (
            select(HouseholdInvitation)
            .where(
                HouseholdInvitation.household_id == household_id,
                HouseholdInvitation.expires_at > effective_now,
                HouseholdInvitation.used_at.is_(None),
                HouseholdInvitation.revoked_at.is_(None),
            )
            .order_by(
                HouseholdInvitation.expires_at.asc(),
                HouseholdInvitation.id.asc(),
            )
        )
        return list(self.db.execute(statement).scalars().all())

    def get_for_household(
        self,
        *,
        invitation_id: UUID,
        household_id: UUID,
    ) -> HouseholdInvitation | None:
        statement = select(HouseholdInvitation).where(
            HouseholdInvitation.id == invitation_id,
            HouseholdInvitation.household_id == household_id,
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

    def consume_and_add_member(
        self,
        invitation: HouseholdInvitation,
        *,
        user_id: UUID,
        used_at: datetime | None = None,
    ) -> HouseholdMember:
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
                used_by_user_id=user_id,
            ),
            execution_options={"synchronize_session": False},
        )
        if getattr(result, "rowcount", 0) != 1:
            self.db.rollback()
            raise HouseholdInvitationNotActiveError

        membership = HouseholdMember(
            household_id=invitation.household_id,
            user_id=user_id,
            role=HouseholdRole.MEMBER,
        )
        self.db.add(membership)
        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise HouseholdMembershipConflictError from error

        self.db.refresh(invitation)
        self.db.refresh(membership)
        return membership


class HouseholdInvitationNotActiveError(ValueError):
    pass


class HouseholdMembershipConflictError(ValueError):
    pass
