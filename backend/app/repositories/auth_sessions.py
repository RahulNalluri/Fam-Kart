from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.auth_session import AuthSession


class AuthSessionRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create(
        self,
        *,
        user_id: UUID,
        refresh_token_hash: str,
        expires_at: datetime,
    ) -> AuthSession:
        auth_session = AuthSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
        )
        self.db.add(auth_session)
        self.db.commit()
        self.db.refresh(auth_session)
        return auth_session

    def get_by_refresh_token_hash(
        self,
        refresh_token_hash: str,
    ) -> AuthSession | None:
        statement = select(AuthSession).where(
            AuthSession.refresh_token_hash == refresh_token_hash,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def revoke(
        self,
        auth_session: AuthSession,
        *,
        revoked_at: datetime | None = None,
    ) -> AuthSession:
        auth_session.revoked_at = revoked_at or datetime.now(UTC)
        self.db.commit()
        self.db.refresh(auth_session)
        return auth_session
