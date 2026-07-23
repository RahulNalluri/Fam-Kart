from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models.household import Household
from app.models.shopping_session import ShoppingSession, ShoppingSessionStatus


class ShoppingSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def lock_household(self, household_id: UUID) -> bool:
        statement = (
            select(Household.id).where(Household.id == household_id).with_for_update()
        )
        return self.db.execute(statement).scalar_one_or_none() is not None

    def create(
        self,
        *,
        household_id: UUID,
        created_by_user_id: UUID,
    ) -> ShoppingSession:
        shopping_session = ShoppingSession(
            household_id=household_id,
            created_by_user_id=created_by_user_id,
            status=ShoppingSessionStatus.ACTIVE,
        )
        self.db.add(shopping_session)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(shopping_session)
        return shopping_session

    def get_active_for_household(
        self,
        household_id: UUID,
    ) -> ShoppingSession | None:
        statement = (
            select(ShoppingSession)
            .where(
                ShoppingSession.household_id == household_id,
                ShoppingSession.status == ShoppingSessionStatus.ACTIVE,
            )
            .order_by(
                ShoppingSession.created_at.desc(),
                ShoppingSession.id.desc(),
            )
            .limit(1)
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_for_household(
        self,
        *,
        session_id: UUID,
        household_id: UUID,
    ) -> ShoppingSession | None:
        statement = select(ShoppingSession).where(
            ShoppingSession.id == session_id,
            ShoppingSession.household_id == household_id,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def list_for_household(self, household_id: UUID) -> list[ShoppingSession]:
        statement = (
            select(ShoppingSession)
            .where(ShoppingSession.household_id == household_id)
            .order_by(
                ShoppingSession.created_at.desc(),
                ShoppingSession.id.desc(),
            )
        )
        return list(self.db.execute(statement).scalars().all())

    def complete(
        self,
        shopping_session: ShoppingSession,
        *,
        completed_at: datetime | None = None,
    ) -> ShoppingSession:
        effective_completed_at = completed_at or datetime.now(UTC)
        try:
            result = self.db.execute(
                update(ShoppingSession)
                .where(
                    ShoppingSession.id == shopping_session.id,
                    ShoppingSession.status == ShoppingSessionStatus.ACTIVE,
                )
                .values(
                    status=ShoppingSessionStatus.COMPLETED,
                    completed_at=effective_completed_at,
                ),
                execution_options={"synchronize_session": False},
            )
        except Exception:
            self.db.rollback()
            raise

        if getattr(result, "rowcount", 0) == 1:
            try:
                self.db.commit()
            except Exception:
                self.db.rollback()
                raise

            self.db.refresh(shopping_session)
            return shopping_session

        self.db.rollback()
        current = self.db.get(ShoppingSession, shopping_session.id)
        if current is not None and current.status == ShoppingSessionStatus.COMPLETED:
            return current
        raise ShoppingSessionNotActiveError


class ShoppingSessionNotActiveError(ValueError):
    pass
