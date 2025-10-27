"""Redis cache service."""

from typing import Any, Optional

import redis.asyncio as redis
from config import get_settings
from crawler.core.logging import get_logger

logger = get_logger(__name__)


class CacheService:
    """Redis cache service for deduplication and rate limiting."""

    def __init__(self) -> None:
        """Initialize cache service."""
        settings = get_settings()
        self.redis = redis.from_url(
            str(settings.redis_url), encoding="utf-8", decode_responses=True
        )
        self.default_ttl = settings.redis_ttl

    async def get(self, key: str) -> Optional[str]:
        """Get value from cache."""
        try:
            return await self.redis.get(key)
        except Exception as e:
            logger.error("cache_get_error", key=key, error=str(e))
            return None

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
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
