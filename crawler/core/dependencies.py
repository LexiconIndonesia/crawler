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
from crawler.services.browser_pool import BrowserPool
from crawler.services.cache import CacheService
from crawler.services.log_publisher import LogPublisher
from crawler.services.memory_monitor import MemoryMonitor
from crawler.services.nats_queue import NATSQueueService
from crawler.services.redis_cache import (
    BrowserPoolStatus,
    JobCancellationFlag,
    JobProgressCache,
    LogBuffer,
    RateLimiter,
    URLDeduplicationCache,
    WebSocketTokenService,
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


async def get_websocket_token_service(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> WebSocketTokenService:
    """Get WebSocket token service with injected dependencies.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        WebSocketTokenService instance
    """
    from crawler.services.redis_cache import WebSocketTokenService

    return WebSocketTokenService(redis_client=redis_client, settings=settings)


async def get_log_buffer(
    redis_client: RedisDep,
    settings: SettingsDep,
) -> LogBuffer:
    """Get log buffer for WebSocket reconnection support.

    Args:
        redis_client: Redis client from dependency
        settings: Application settings from dependency

    Returns:
        LogBuffer instance
    """
    from crawler.services.redis_cache import LogBuffer

    return LogBuffer(redis_client=redis_client, settings=settings)


# Global browser pool instance (singleton pattern)
_browser_pool: BrowserPool | None = None

# Global NATS queue service instance (singleton pattern)
_nats_queue_service: NATSQueueService | None = None

# Global memory monitor instance (singleton pattern)
_memory_monitor: MemoryMonitor | None = None


async def get_browser_pool(
    settings: SettingsDep,
) -> BrowserPool:
    """Get browser pool with singleton pattern.

    The pool is created once and reused across requests.
    Pool is initialized at app startup and closed at shutdown.

    Args:
        settings: Application settings from dependency

    Returns:
        BrowserPool instance

    Usage:
        async def my_route(browser_pool: BrowserPoolDep):
            async with browser_pool.acquire_context() as context:
                page = await context.new_page()
    """
    global _browser_pool

    # Guard: return existing instance if available
    if _browser_pool is not None:
        return _browser_pool

    # Create new instance
    from crawler.services.browser_pool import BrowserPool

    _browser_pool = BrowserPool(settings=settings)
    return _browser_pool


async def get_nats_queue_service(
    settings: SettingsDep,
) -> NATSQueueService:
    """Get NATS queue service with singleton pattern.

    The service is created once and reused across requests.
    Connection is established at app startup and closed at shutdown.

    Args:
        settings: Application settings from dependency

    Returns:
        NATSQueueService instance

    Usage:
        async def my_route(nats_queue: NATSQueueDep):
            await nats_queue.publish_job(job_id, job_data)
    """
    global _nats_queue_service

    # Guard: return existing instance if available
    if _nats_queue_service is not None:
        return _nats_queue_service

    # Create new instance
    from crawler.services.nats_queue import NATSQueueService

    _nats_queue_service = NATSQueueService(settings=settings)
    return _nats_queue_service


async def get_log_publisher(
    nats_queue_service: NATSQueueDep,
    log_buffer: LogBufferDep,
) -> LogPublisher:
    """Get log publisher for real-time log streaming via NATS with Redis buffering.

    The log publisher uses the NATS client from the queue service
    to publish logs to NATS subjects for WebSocket consumption.
    It also buffers logs in Redis for reconnection support.

    Args:
        nats_queue_service: NATS queue service (provides NATS client)
        log_buffer: Redis-based log buffer for reconnection support

    Returns:
        LogPublisher instance

    Usage:
        async def my_handler(log_publisher: LogPublisherDep):
            await log_publisher.publish_log(log)
    """
    from crawler.services.log_publisher import LogPublisher

    # Get NATS client from queue service (may be None if not connected)
    nats_client = nats_queue_service.client if nats_queue_service else None
    return LogPublisher(nats_client=nats_client, log_buffer=log_buffer)


async def initialize_browser_pool() -> None:
    """Initialize browser pool at application startup.

    Should be called in FastAPI lifespan startup.
    """
    settings = get_settings()
    pool = await get_browser_pool(settings)
    await pool.initialize()


async def shutdown_browser_pool() -> None:
    """Shutdown browser pool at application shutdown.

    Should be called in FastAPI lifespan shutdown.
    """
    global _browser_pool
    if _browser_pool is not None:
        await _browser_pool.shutdown()
        _browser_pool = None


async def connect_nats_queue() -> None:
    """Connect NATS queue service at application startup.

    Should be called in FastAPI lifespan startup.
    """
    settings = get_settings()
    service = await get_nats_queue_service(settings)
    await service.connect()


async def disconnect_nats_queue() -> None:
    """Disconnect NATS queue service at application shutdown.

    Should be called in FastAPI lifespan shutdown.
    """
    global _nats_queue_service
    if _nats_queue_service is not None:
        await _nats_queue_service.disconnect()
        _nats_queue_service = None


async def get_memory_monitor(
    settings: SettingsDep,
) -> MemoryMonitor:
    """Get memory monitor with singleton pattern.

    The monitor is created once and reused across requests.
    Monitor is started at app startup and stopped at shutdown.

    Args:
        settings: Application settings from dependency

    Returns:
        MemoryMonitor instance

    Usage:
        async def my_route(memory_monitor: MemoryMonitorDep):
            status = await memory_monitor.check_memory()
    """
    global _memory_monitor

    # Guard: return existing instance if available
    if _memory_monitor is not None:
        return _memory_monitor

    # Create new instance
    from crawler.services.memory_monitor import MemoryMonitor

    # Get browser pool if available
    browser_pool = await get_browser_pool(settings) if _browser_pool is not None else None

    _memory_monitor = MemoryMonitor(
        browser_pool=browser_pool,
        check_interval=30.0,  # Check every 30 seconds
    )
    return _memory_monitor


async def start_memory_monitor() -> None:
    """Start memory monitor at application startup.

    Should be called in FastAPI lifespan startup after browser pool initialization.
    """
    settings = get_settings()
    monitor = await get_memory_monitor(settings)
    await monitor.start()


async def stop_memory_monitor() -> None:
    """Stop memory monitor at application shutdown.

    Should be called in FastAPI lifespan shutdown.
    """
    global _memory_monitor
    if _memory_monitor is not None:
        await _memory_monitor.stop()
        _memory_monitor = None


# ============================================================================
# Service Type Aliases for Dependency Injection
# ============================================================================

# Service dependencies
CacheServiceDep = Annotated[CacheService, Depends(get_cache_service)]
StorageServiceDep = Annotated[StorageService, Depends(get_storage_service)]
BrowserPoolDep = Annotated[BrowserPool, Depends(get_browser_pool)]
NATSQueueDep = Annotated[NATSQueueService, Depends(get_nats_queue_service)]
LogPublisherDep = Annotated[LogPublisher, Depends(get_log_publisher)]
MemoryMonitorDep = Annotated[MemoryMonitor, Depends(get_memory_monitor)]
URLDedupCacheDep = Annotated[URLDeduplicationCache, Depends(get_url_dedup_cache)]
JobCancellationFlagDep = Annotated[JobCancellationFlag, Depends(get_job_cancellation_flag)]
RateLimiterDep = Annotated[RateLimiter, Depends(get_rate_limiter)]
BrowserPoolStatusDep = Annotated[BrowserPoolStatus, Depends(get_browser_pool_status)]
JobProgressCacheDep = Annotated[JobProgressCache, Depends(get_job_progress_cache)]
WebSocketTokenServiceDep = Annotated[WebSocketTokenService, Depends(get_websocket_token_service)]
LogBufferDep = Annotated[LogBuffer, Depends(get_log_buffer)]
