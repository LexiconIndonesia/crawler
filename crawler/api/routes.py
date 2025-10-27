"""API routes."""

from datetime import UTC, datetime

import redis.asyncio as redis
from fastapi import APIRouter, Depends
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import Response

from config import get_settings
from crawler.db import get_db

router = APIRouter()


@router.get("/")
async def root() -> dict[str, str]:
    """Root endpoint."""
    settings = get_settings()
    return {
        "message": f"Welcome to {settings.app_name}",
        "version": settings.app_version,
        "environment": settings.environment,
    }


@router.get("/health")
async def health(db: AsyncSession = Depends(get_db)) -> dict[str, str | dict[str, str]]:
    """Health check endpoint with database and Redis connectivity checks."""
    health_status = {
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
    settings = get_settings()
    redis_client = None
    try:
        redis_client = redis.from_url(
            str(settings.redis_url), encoding="utf-8", decode_responses=True
        )
        await redis_client.ping()
        health_status["checks"]["redis"] = "connected"
    except Exception as e:
        health_status["status"] = "unhealthy"
        health_status["checks"]["redis"] = f"error: {str(e)}"
    finally:
        if redis_client:
            await redis_client.close()

    return health_status


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
