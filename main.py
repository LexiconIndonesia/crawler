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
    start_retry_scheduler_service,
    start_scheduled_job_processor_service,
    stop_memory_monitor,
    stop_retry_scheduler_service,
    stop_scheduled_job_processor_service,
)
from crawler.core.logging import get_logger
from crawler.services.dlq_metrics_updater import start_dlq_metrics_updater, stop_dlq_metrics_updater

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

    # Start DLQ metrics updater
    try:
        await start_dlq_metrics_updater(interval_seconds=60)
        logger.info("dlq_metrics_updater_started")
    except Exception as e:
        logger.error("dlq_metrics_updater_start_failed_on_startup", error=str(e))
        # Continue without DLQ metrics - app can still function

    # Start retry scheduler (non-blocking retry delays)
    try:
        await start_retry_scheduler_service(interval_seconds=5, batch_size=100)
        logger.info("retry_scheduler_started")
    except Exception as e:
        logger.error("retry_scheduler_start_failed_on_startup", error=str(e))
        # Continue without retry scheduler - will fall back to blocking sleep

    # Start scheduled job processor (creates crawl jobs from scheduled jobs)
    try:
        await start_scheduled_job_processor_service(interval_seconds=60, batch_size=100)
        logger.info("scheduled_job_processor_started")
    except Exception as e:
        logger.error("scheduled_job_processor_start_failed_on_startup", error=str(e))
        # Continue without scheduled job processor - scheduled jobs won't be auto-executed

    yield

    # Shutdown
    logger.info("application_shutdown")

    # Stop scheduled job processor first (before database shutdown)
    try:
        await stop_scheduled_job_processor_service()
        logger.info("scheduled_job_processor_stopped")
    except Exception as e:
        logger.error("scheduled_job_processor_stop_failed_on_shutdown", error=str(e))

    # Stop retry scheduler (before NATS/Redis)
    try:
        await stop_retry_scheduler_service()
        logger.info("retry_scheduler_stopped")
    except Exception as e:
        logger.error("retry_scheduler_stop_failed_on_shutdown", error=str(e))

    # Stop DLQ metrics updater
    try:
        await stop_dlq_metrics_updater()
        logger.info("dlq_metrics_updater_stopped")
    except Exception as e:
        logger.error("dlq_metrics_updater_stop_failed_on_shutdown", error=str(e))

    # Stop memory monitor
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
