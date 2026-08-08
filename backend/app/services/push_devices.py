from uuid import UUID

from app.models.push_device import PushDevice
from app.models.user import User
from app.repositories.push_devices import (
    PushDeviceRegistrationConflictError,
    PushDeviceRepository,
)
from app.schemas.push_devices import RegisterPushDeviceRequest


class DeviceAlreadyRegisteredError(ValueError):
    pass


def register_push_device(
    data: RegisterPushDeviceRequest,
    user: User,
    repository: PushDeviceRepository,
) -> PushDevice:
    try:
        return repository.register(
            user_id=user.id,
            installation_id=data.installation_id,
            expo_push_token=data.expo_push_token,
            platform=data.platform,
        )
    except PushDeviceRegistrationConflictError as error:
        raise DeviceAlreadyRegisteredError from error


def deactivate_push_device(
    installation_id: UUID,
    user: User,
    repository: PushDeviceRepository,
) -> None:
    repository.deactivate_for_user(
        user_id=user.id,
        installation_id=installation_id,
    )
