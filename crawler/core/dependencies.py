"""Centralized dependency injection for the application.

This module provides all dependency injection functions and type aliases
used throughout the application. It serves as a single source of truth
for all dependencies.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Annotated

import redis.asyncio as redis
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from config import Settings, get_settings
from crawler.cache.session import get_redis as _get_redis
from crawler.db.session import get_db as _get_db
from crawler.services.cache import CacheService
from crawler.services.redis_cache import (
    BrowserPoolStatus,
    JobCancellationFlag,
    JobProgressCache,
    RateLimiter,
    URLDeduplicationCache,
)
from crawler.services.storage import StorageService

# ============================================================================
# Core Dependencies
# ============================================================================


def get_app_settings() -> Settings:
    """Get application settings.

    Returns:
        Application settings instance

    Usage:
        async def my_route(settings: SettingsDep):
            print(settings.app_name)
    """
    return get_settings()


async def get_database() -> AsyncGenerator[AsyncSession, None]:
    """Get database session.

    Yields:
        Async database session with automatic transaction management

    Usage:
        async def my_route(db: DBSessionDep):
            result = await db.execute(...)
    """
    async for session in _get_db():
        yield session


async def get_redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Get Redis client.

    Yields:
        Redis client with connection pooling

    Usage:
        async def my_route(redis_client: RedisDep):
            await redis_client.set("key", "value")
    """
    async for client in _get_redis():
        yield client


# ============================================================================
# Type Aliases for Dependency Injection (defined before use)
# ============================================================================

# Settings dependency
SettingsDep = Annotated[Settings, Depends(get_app_settings)]

# Database session dependency
DBSessionDep = Annotated[AsyncSession, Depends(get_database)]

# Redis client dependency
RedisDep = Annotated[redis.Redis, Depends(get_redis_client)]


# ============================================================================
# Service Factory Dependencies
# ============================================================================


async def get_cache_service(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> CacheService:
    """Get cache service with injected dependencies.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        CacheService instance

    Usage:
        async def my_route(cache: CacheServiceDep):
            await cache.set("key", "value")
    """
    from crawler.services.cache import CacheService

    return CacheService(redis_client=redis_client, settings=settings)


async def get_storage_service(
    settings: SettingsDep,
) -> StorageService:
    """Get storage service with injected dependencies.

    Args:
        settings: Application settings from dependency

    Returns:
        StorageService instance

    Usage:
        async def my_route(storage: StorageServiceDep):
            await storage.upload_html(url, content, task_id)
    """
    from crawler.services.storage import StorageService

    return StorageService(settings=settings)


async def get_url_dedup_cache(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> URLDeduplicationCache:
    """Get URL deduplication cache with injected dependencies.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        URLDeduplicationCache instance
    """
    from crawler.services.redis_cache import URLDeduplicationCache

    return URLDeduplicationCache(redis_client=redis_client, settings=settings)


async def get_job_cancellation_flag(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> JobCancellationFlag:
    """Get job cancellation flag with injected dependencies.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        JobCancellationFlag instance
    """
    from crawler.services.redis_cache import JobCancellationFlag

    return JobCancellationFlag(redis_client=redis_client, settings=settings)


async def get_rate_limiter(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> RateLimiter:
    """Get rate limiter with injected dependencies.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        RateLimiter instance
    """
    from crawler.services.redis_cache import RateLimiter

    return RateLimiter(redis_client=redis_client, settings=settings)


async def get_browser_pool_status(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> BrowserPoolStatus:
    """Get browser pool status tracker with injected dependencies.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        BrowserPoolStatus instance
    """
    from crawler.services.redis_cache import BrowserPoolStatus

    return BrowserPoolStatus(redis_client=redis_client, settings=settings)


async def get_job_progress_cache(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> JobProgressCache:
    """Get job progress cache with injected dependencies.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        JobProgressCache instance
    """
    from crawler.services.redis_cache import JobProgressCache

    return JobProgressCache(redis_client=redis_client, settings=settings)


# ============================================================================
# Service Type Aliases for Dependency Injection
# ============================================================================

# Service dependencies
CacheServiceDep = Annotated[CacheService, Depends(get_cache_service)]
StorageServiceDep = Annotated[StorageService, Depends(get_storage_service)]
URLDedupCacheDep = Annotated[URLDeduplicationCache, Depends(get_url_dedup_cache)]
JobCancellationFlagDep = Annotated[JobCancellationFlag, Depends(get_job_cancellation_flag)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
BrowserPoolStatusDep = Annotated[BrowserPoolStatus, Depends(get_browser_pool_status)]
JobProgressCacheDep = Annotated[JobProgressCache, Depends(get_job_progress_cache)]
