from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.push_device import PushDevice, PushPlatform


class PushDeviceRegistrationConflictError(ValueError):
    pass


class PushDeviceRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_installation_id(self, installation_id: UUID) -> PushDevice | None:
        statement = select(PushDevice).where(
            PushDevice.installation_id == installation_id,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def get_by_expo_push_token(self, expo_push_token: str) -> PushDevice | None:
        statement = select(PushDevice).where(
            PushDevice.expo_push_token == expo_push_token,
        )
        return self.db.execute(statement).scalar_one_or_none()

    def register(
        self,
        *,
        user_id: UUID,
        installation_id: UUID,
        expo_push_token: str,
        platform: PushPlatform,
        registered_at: datetime | None = None,
    ) -> PushDevice:
        effective_registered_at = registered_at or datetime.now(UTC)
        device = self.get_by_installation_id(installation_id)
        token_owner = self.get_by_expo_push_token(expo_push_token)

        if device is not None and device.user_id != user_id and device.is_active:
            if device.expo_push_token != expo_push_token:
                raise PushDeviceRegistrationConflictError
        if (
            token_owner is not None
            and token_owner is not device
            and token_owner.is_active
        ):
            raise PushDeviceRegistrationConflictError
        if device is not None and token_owner is not None and token_owner is not device:
            self.db.delete(token_owner)
            self.db.flush()

        if device is None:
            device = token_owner or PushDevice(installation_id=installation_id)
            self.db.add(device)

        device.user_id = user_id
        device.installation_id = installation_id
        device.expo_push_token = expo_push_token
        device.platform = platform
        device.is_active = True
        device.last_registered_at = effective_registered_at
        device.deactivated_at = None

        try:
            self.db.commit()
        except IntegrityError as error:
            self.db.rollback()
            raise PushDeviceRegistrationConflictError from error
        except Exception:
            self.db.rollback()
            raise

        self.db.refresh(device)
        return device

    def deactivate_for_user(
        self,
        *,
        user_id: UUID,
        installation_id: UUID,
        deactivated_at: datetime | None = None,
    ) -> bool:
        device = self.get_by_installation_id(installation_id)
        if device is None or device.user_id != user_id or not device.is_active:
            return False

        device.is_active = False
        device.deactivated_at = deactivated_at or datetime.now(UTC)
        try:
            self.db.commit()
        except Exception:
            self.db.rollback()
            raise
        return True
