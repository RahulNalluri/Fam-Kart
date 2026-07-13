from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db
from app.schemas.common import DatabaseHealthResponse, HealthResponse
from app.services.health import is_database_healthy

router = APIRouter(prefix="/api/v1", tags=["health"])


@router.get("/health", response_model=HealthResponse)
def read_health() -> HealthResponse:
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        version=settings.version,
    )


@router.get("/health/database", response_model=DatabaseHealthResponse)
def read_database_health(
    db: Annotated[Session, Depends(get_db)],
) -> DatabaseHealthResponse:
    try:
        is_healthy = is_database_healthy(db)
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc

    if not is_healthy:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        )

    return DatabaseHealthResponse(status="healthy", database="postgresql")
