from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, WebSocket
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.household_members import HouseholdMemberRepository
from app.repositories.users import UserRepository
from app.schemas.realtime import RealtimeCloseCode
from app.services.realtime import (
    RealtimeAuthenticationError,
    RealtimeHouseholdNotFoundError,
    authenticate_realtime_connection,
)

router = APIRouter(tags=["real-time"])

AUTHENTICATION_REQUIRED_REASON = "Authentication required."
HOUSEHOLD_NOT_FOUND_REASON = "Household not found."


@router.websocket("/api/v1/households/{household_id}/ws")
async def household_realtime_connection(
    websocket: WebSocket,
    household_id: UUID,
    db: Annotated[Session, Depends(get_db)],
) -> None:
    try:
        authenticate_realtime_connection(
            websocket.headers.get("authorization"),
            household_id,
            UserRepository(db),
            HouseholdMemberRepository(db),
        )
    except RealtimeAuthenticationError:
        await _reject_connection(
            websocket,
            RealtimeCloseCode.AUTHENTICATION_REQUIRED,
            AUTHENTICATION_REQUIRED_REASON,
        )
        return
    except RealtimeHouseholdNotFoundError:
        await _reject_connection(
            websocket,
            RealtimeCloseCode.HOUSEHOLD_NOT_FOUND,
            HOUSEHOLD_NOT_FOUND_REASON,
        )
        return
    finally:
        db.close()

    await websocket.accept()
    while True:
        message = await websocket.receive()
        if message["type"] == "websocket.disconnect":
            return


async def _reject_connection(
    websocket: WebSocket,
    code: RealtimeCloseCode,
    reason: str,
) -> None:
    await websocket.accept()
    await websocket.close(code=int(code), reason=reason)
