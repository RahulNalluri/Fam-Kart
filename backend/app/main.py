from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.auth import router as auth_router
from app.api.grocery_items import router as grocery_items_router
from app.api.grocery_parsing import router as grocery_parsing_router
from app.api.health import router as health_router
from app.api.household_grocery_aliases import router as household_grocery_aliases_router
from app.api.households import router as households_router
from app.api.push_devices import router as push_devices_router
from app.api.realtime import router as realtime_router
from app.api.shopping_sessions import router as shopping_sessions_router
from app.api.users import router as users_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.http import create_http_client
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.redis import create_redis_client
from app.services.realtime_connections import connection_manager
from app.services.realtime_subscription_coordinator import (
    RealtimeSubscriptionCoordinator,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    redis_client = create_redis_client()
    http_client = create_http_client()
    subscription_coordinator = RealtimeSubscriptionCoordinator(
        redis_client,
        connection_manager,
    )
    app.state.redis = redis_client
    app.state.http_client = http_client
    app.state.realtime_subscriptions = subscription_coordinator
    try:
        yield
    finally:
        await subscription_coordinator.shutdown()
        await http_client.aclose()
        await redis_client.aclose()


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=settings.version,
        description="Backend API for FamilyKart AI.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)
    app.include_router(auth_router)
    app.include_router(health_router)
    app.include_router(households_router)
    app.include_router(household_grocery_aliases_router)
    app.include_router(shopping_sessions_router)
    app.include_router(grocery_parsing_router)
    app.include_router(grocery_items_router)
    app.include_router(push_devices_router)
    app.include_router(realtime_router)
    app.include_router(users_router)
    return app


app = create_app()
