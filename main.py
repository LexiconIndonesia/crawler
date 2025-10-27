"""Lexicon Crawler main application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crawler.api import router, router_v1
from crawler.core import setup_logging
from crawler.core.dependencies import get_app_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles application startup and shutdown events.
    """
    # Startup
    setup_logging()
    yield
    # Shutdown
    pass


def create_app() -> FastAPI:
    """Create and configure FastAPI application.

    Uses centralized dependency injection for settings.
    """
    # Get settings for app initialization
    # This is acceptable here as we need settings before the app is created
    settings = get_app_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Lexicon Crawler API",
        version=settings.app_version,
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(router)  # Non-versioned endpoints (root, health, metrics)
    app.include_router(router_v1)  # API v1 endpoints

    return app


app = create_app()
