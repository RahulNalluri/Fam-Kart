from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.push_devices import PushDeviceRepository
from app.schemas.push_devices import PushDeviceResponse, RegisterPushDeviceRequest
from app.services.push_devices import (
    DeviceAlreadyRegisteredError,
    deactivate_push_device,
    register_push_device,
)

router = APIRouter(
    prefix="/api/v1/users/me/push-devices",
    tags=["push devices"],
)


@router.put("", response_model=PushDeviceResponse)
def register_current_push_device(
    data: RegisterPushDeviceRequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> PushDeviceResponse:
    try:
        device = register_push_device(
            data,
            current_user,
            PushDeviceRepository(db),
        )
    except DeviceAlreadyRegisteredError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This device is already registered to another account.",
        ) from error
    return PushDeviceResponse.model_validate(device)


@router.delete("/{installation_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_current_push_device(
    installation_id: UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
) -> Response:
    deactivate_push_device(
        installation_id,
        current_user,
        PushDeviceRepository(db),
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
