"""Base API routes (non-versioned endpoints)."""

from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from config import get_settings
from crawler.api.schemas import HealthResponse, RootResponse
from crawler.cache import get_redis
from crawler.db import get_db

router = APIRouter()


@router.get(
    "/",
    response_model=RootResponse,
    summary="Root endpoint",
    description="Returns basic application information including name, version, and environment",
    tags=["General"],
)
async def root() -> RootResponse:
    """Root endpoint."""
    settings = get_settings()
    return RootResponse(
        message=f"Welcome to {settings.app_name}",
        version=settings.app_version,
        environment=settings.environment,
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check the health status of the application including database and Redis",
    tags=["General"],
    responses={
        200: {
            "description": "Health check results",
            "content": {
                "application/json": {
                    "examples": {
                        "healthy": {
                            "value": {
                                "status": "healthy",
                                "timestamp": "2025-10-27T10:00:00Z",
                                "checks": {"database": "connected", "redis": "connected"},
                            }
                        },
                        "unhealthy": {
                            "value": {
                                "status": "unhealthy",
                                "timestamp": "2025-10-27T10:00:00Z",
                                "checks": {
                                    "database": "error: connection timeout",
                                    "redis": "connected",
                                },
                            }
                        },
                    }
                }
            },
        }
    },
)
async def health(
    db: AsyncSession = Depends(get_db),
    redis_client: redis.Redis = Depends(get_redis),
) -> HealthResponse:
    """Health check endpoint with database and Redis connectivity checks."""
    health_status: dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.now(UTC).isoformat(),
        "checks": {},
    }

    # Check PostgreSQL connection
    try:
        await db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = "connected"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["database"] = f"error: {str(e)}"

    # Check Redis connection
    try:
        await redis_client.ping()
        health_status["checks"]["redis"] = "connected"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = f"error: {str(e)}"

    return HealthResponse(**health_status)


@router.get(
    "/metrics",
    summary="Prometheus metrics",
    description="Expose Prometheus metrics for monitoring",
    tags=["Monitoring"],
    response_class=Response,
)
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
