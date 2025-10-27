"""Redis cache service."""

from typing import Any

import redis.asyncio as redis

from config import Settings
from crawler.core.logging import get_logger

logger = get_logger(__name__)


class CacheService:
    """Redis cache service for deduplication and rate limiting."""

    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Initialize cache service with injected dependencies.

        Args:
            redis_client: Redis client instance
            settings: Application settings
        """
        self.redis = redis_client
        self.default_ttl = settings.redis_ttl

    async def get(self, key: str) -> str | None:
        """Get value from cache."""
        try:
            result: str | None = await self.redis.get(key)
            return result
        except Exception as e:
            logger.error("cache_get_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: int | None = None) -> bool:
        """Set value in cache with TTL."""
        try:
            ttl = ttl or self.default_ttl
            await self.redis.setex(key, ttl, str(value))
            return True
        except Exception as e:
            logger.error("cache_set_error", key=key, error=str(e))
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error("cache_exists_error", key=key, error=str(e))
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            await self.redis.delete(key)
            return True
        except Exception as e:
            logger.error("cache_delete_error", key=key, error=str(e))
            return False

    async def close(self) -> None:
        """Close Redis connection."""
        await self.redis.close()
