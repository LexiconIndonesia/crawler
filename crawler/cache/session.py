"""Redis connection pool management."""

from collections.abc import AsyncGenerator

import redis.asyncio as redis

from config import get_settings

settings = get_settings()

# Create Redis connection pool
redis_pool: redis.ConnectionPool = redis.ConnectionPool.from_url(
    str(settings.redis_url),
    encoding="utf-8",
    decode_responses=True,
    max_connections=settings.redis_max_connections,
)


async def get_redis() -> AsyncGenerator[redis.Redis, None]:
    """Get Redis client dependency with connection pooling.

    This dependency provides a Redis client that uses connection pooling
    for efficient resource management. The connection is automatically
    returned to the pool after use.

    Yields:
        Redis client instance from the connection pool.

    Example:
        ```python
        @router.get("/health")
        async def health(redis = Depends(get_redis)):
            await redis.ping()
            return {"status": "ok"}
        ```
    """
    client = redis.Redis(connection_pool=redis_pool)
    try:
        yield client
    finally:
        await client.aclose()  # type: ignore[attr-defined]
