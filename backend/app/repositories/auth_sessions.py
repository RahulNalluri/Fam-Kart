from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
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

    def rotate(
        self,
        auth_session: AuthSession,
        *,
        new_refresh_token_hash: str,
        new_expires_at: datetime,
        rotated_at: datetime,
    ) -> AuthSession:
        result = self.db.execute(
            update(AuthSession)
            .where(
                AuthSession.id == auth_session.id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > rotated_at,
            )
            .values(revoked_at=rotated_at),
            execution_options={"synchronize_session": False},
        )
        if getattr(result, "rowcount", 0) != 1:
            self.db.rollback()
            raise AuthSessionNotActiveError

        replacement = AuthSession(
            user_id=auth_session.user_id,
            refresh_token_hash=new_refresh_token_hash,
            expires_at=new_expires_at,
        )
        self.db.add(replacement)
        self.db.commit()
        self.db.refresh(replacement)
        return replacement


class AuthSessionNotActiveError(ValueError):
    pass
