"""Base API routes (non-versioned endpoints)."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.responses import Response

from crawler.api.generated import Environment, HealthResponse, RootResponse
from crawler.core.dependencies import DBSessionDep, RedisDep, SettingsDep

router = APIRouter()


@router.get(
    "/",
    response_model=RootResponse,
    summary="Root endpoint",
    description="Returns basic application information including name, version, and environment",
    tags=["General"],
    operation_id="getRoot",
)
async def root(settings: SettingsDep) -> RootResponse:
    """Root endpoint with injected settings.

    Args:
        settings: Application settings from dependency injection
    """
    return RootResponse(
        message=f"Welcome to {settings.app_name}",
        version=settings.app_version,
        environment=Environment(settings.environment),
    )


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check the health status of the application including database and Redis",
    tags=["General"],
    operation_id="healthCheck",
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
    db: DBSessionDep,
    redis_client: RedisDep,
) -> HealthResponse:
    """Health check endpoint with database and Redis connectivity checks.

    Args:
        db: Database session from dependency injection
        redis_client: Redis client from dependency injection
    """
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
    operation_id="getMetrics",
    response_class=Response,
)
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
