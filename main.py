"""Lexicon Crawler main application."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from crawler.api import router, router_v1
from crawler.api.websocket import router as websocket_router
from crawler.core import setup_logging
from crawler.core.dependencies import (
    connect_nats_queue,
    disconnect_nats_queue,
    get_app_settings,
    initialize_browser_pool,
    shutdown_browser_pool,
    start_memory_monitor,
    stop_memory_monitor,
)
from crawler.core.logging import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan manager.

    Handles application startup and shutdown events.
    """
    # Startup
    setup_logging()
    logger.info("application_startup", app_name=app.title, version=app.version)

    # Initialize browser pool
    try:
        await initialize_browser_pool()
        logger.info("browser_pool_initialized")
    except Exception as e:
        logger.error("browser_pool_initialization_failed_on_startup", error=str(e))
        # Continue without browser pool - browser executor will fall back to per-request browsers

    # Connect to NATS queue
    try:
        await connect_nats_queue()
        logger.info("nats_queue_connected")
    except Exception as e:
        logger.error("nats_connection_failed_on_startup", error=str(e))
        # Continue without NATS - database polling can still work as fallback

    # Start memory monitoring
    try:
        await start_memory_monitor()
        logger.info("memory_monitor_started")
    except Exception as e:
        logger.error("memory_monitor_start_failed_on_startup", error=str(e))
        # Continue without memory monitoring - app can still function

    yield

    # Shutdown
    logger.info("application_shutdown")

    # Stop memory monitor first
    try:
        await stop_memory_monitor()
        logger.info("memory_monitor_stopped")
    except Exception as e:
        logger.error("memory_monitor_stop_failed_on_shutdown", error=str(e))

    try:
        await shutdown_browser_pool()
        logger.info("browser_pool_shutdown")
    except Exception as e:
        logger.error("browser_pool_shutdown_failed", error=str(e))

    try:
        await disconnect_nats_queue()
        logger.info("nats_queue_disconnected")
    except Exception as e:
        logger.error("nats_disconnect_failed_on_shutdown", error=str(e))


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
    app.include_router(websocket_router)  # WebSocket endpoints (/ws/v1)

    return app


app = create_app()
