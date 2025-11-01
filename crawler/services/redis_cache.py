"""Redis cache services for crawler operations.

Provides specialized Redis data structures for:
- URL deduplication
- Job cancellation flags
- Rate limiting
- Browser pool status tracking
- Job progress caching
"""

import builtins
import json
from typing import Any, cast

import redis.asyncio as redis

from config import Settings
from crawler.core.logging import get_logger
from crawler.utils import hash_url

logger = get_logger(__name__)


class URLDeduplicationCache:
    """Redis-based URL deduplication cache.

    Uses URL hashes as keys to track which URLs have been crawled.
    Supports TTL-based expiration for temporary deduplication windows.
    """

    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Initialize URL deduplication cache.

        Args:
            redis_client: Redis client from connection pool.
            settings: Application settings.
        """
        self.settings = settings
        self.redis = redis_client
        self.key_prefix = "url:dedup:"

    def _make_key(self, url_hash: str) -> str:
        """Create Redis key for URL hash.

        Args:
            url_hash: SHA256 hash of URL.

        Returns:
            Redis key string.
        """
        return f"{self.key_prefix}{url_hash}"

    async def set(self, url_hash: str, data: dict[str, Any], ttl: int | None = None) -> bool:
        """Mark URL as seen with associated data.

        Args:
            url_hash: SHA256 hash of URL.
            data: Associated metadata (job_id, crawled_at, etc.).
            ttl: Time to live in seconds. Defaults to settings.redis_ttl.

        Returns:
            True if successful, False otherwise.
        """
        try:
            key = self._make_key(url_hash)
            ttl = ttl or self.settings.redis_ttl
            value = json.dumps(data)
            await self.redis.setex(key, ttl, value)
            logger.debug("url_dedup_set", url_hash=url_hash, ttl=ttl)
            return True
        except Exception as e:
            logger.error("url_dedup_set_error", url_hash=url_hash, error=str(e))
            return False

    async def get(self, url_hash: str) -> dict[str, Any] | None:
        """Get data for a URL hash.

        Args:
            url_hash: SHA256 hash of URL.

        Returns:
            Associated data if exists, None otherwise.
        """
        try:
            key = self._make_key(url_hash)
            value: str | None = await self.redis.get(key)
            if value:
                return cast(dict[str, Any], json.loads(value))
            return None
        except Exception as e:
            logger.error("url_dedup_get_error", url_hash=url_hash, error=str(e))
            return None

    async def exists(self, url_hash: str) -> bool:
        """Check if URL hash exists in cache.

        Args:
            url_hash: SHA256 hash of URL.

        Returns:
            True if exists, False otherwise.
        """
        try:
            key = self._make_key(url_hash)
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error("url_dedup_exists_error", url_hash=url_hash, error=str(e))
            return False

    async def delete(self, url_hash: str) -> bool:
        """Remove URL hash from cache.

        Args:
            url_hash: SHA256 hash of URL.

        Returns:
            True if successful, False otherwise.
        """
        try:
            key = self._make_key(url_hash)
            await self.redis.delete(key)
            logger.debug("url_dedup_deleted", url_hash=url_hash)
            return True
        except Exception as e:
            logger.error("url_dedup_delete_error", url_hash=url_hash, error=str(e))
            return False

    async def set_url(self, url: str, data: dict[str, Any], ttl: int | None = None) -> bool:
        """Mark URL as seen with associated data (auto-normalizes and hashes).

        This is a convenience method that automatically normalizes the URL
        and generates its hash before storing.

        Args:
            url: The URL to mark as seen (will be normalized).
            data: Associated metadata (job_id, crawled_at, etc.).
            ttl: Time to live in seconds. Defaults to settings.redis_ttl.

        Returns:
            True if successful, False otherwise.
        """
        try:
            url_hash = hash_url(url, normalize=True)
            return await self.set(url_hash, data, ttl)
        except Exception as e:
            logger.error("url_dedup_set_url_error", url=url, error=str(e))
            return False

    async def get_url(self, url: str) -> dict[str, Any] | None:
        """Get data for a URL (auto-normalizes and hashes).

        This is a convenience method that automatically normalizes the URL
        and generates its hash before lookup.

        Args:
            url: The URL to look up (will be normalized).

        Returns:
            Associated data if exists, None otherwise.
        """
        try:
            url_hash = hash_url(url, normalize=True)
            return await self.get(url_hash)
        except Exception as e:
            logger.error("url_dedup_get_url_error", url=url, error=str(e))
            return None

    async def exists_url(self, url: str) -> bool:
        """Check if URL exists in cache (auto-normalizes and hashes).

        This is a convenience method that automatically normalizes the URL
        and generates its hash before checking.

        Args:
            url: The URL to check (will be normalized).

        Returns:
            True if exists, False otherwise.
        """
        try:
            url_hash = hash_url(url, normalize=True)
            return await self.exists(url_hash)
        except Exception as e:
            logger.error("url_dedup_exists_url_error", url=url, error=str(e))
            return False

    async def delete_url(self, url: str) -> bool:
        """Remove URL from cache (auto-normalizes and hashes).

        This is a convenience method that automatically normalizes the URL
        and generates its hash before deletion.

        Args:
            url: The URL to remove (will be normalized).

        Returns:
            True if successful, False otherwise.
        """
        try:
            url_hash = hash_url(url, normalize=True)
            return await self.delete(url_hash)
        except Exception as e:
            logger.error("url_dedup_delete_url_error", url=url, error=str(e))
            return False

    async def exists_batch(self, url_hashes: list[str]) -> builtins.set[str]:
        """Check if multiple URL hashes exist in cache (batch operation).

        This method is more efficient than checking each hash individually
        as it uses a single Redis MGET command.

        Args:
            url_hashes: List of SHA256 hashes to check.

        Returns:
            Set of URL hashes that exist in the cache.
        """
        if not url_hashes:
            return set()

        try:
            # Create Redis keys for all hashes
            keys = [self._make_key(url_hash) for url_hash in url_hashes]

            # Use MGET to check all keys in one network round trip
            values = await self.redis.mget(keys)

            # Collect hashes that have values (exist in cache)
            existing_hashes = {
                url_hash for url_hash, value in zip(url_hashes, values) if value is not None
            }

            logger.debug(
                "url_dedup_batch_check",
                checked_count=len(url_hashes),
                existing_count=len(existing_hashes),
            )
            return existing_hashes

        except Exception as e:
            logger.error("url_dedup_batch_check_error", hash_count=len(url_hashes), error=str(e))
            # Fall back to individual checks if batch fails
            existing = set()
            for url_hash in url_hashes:
                if await self.exists(url_hash):
                    existing.add(url_hash)
            return existing


class JobCancellationFlag:
    """Redis-based job cancellation flags.

    Provides fast in-memory flags for checking if a job should be cancelled.
    Workers can poll these flags during execution.
    """

    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Initialize job cancellation flag service.

        Args:
            redis_client: Redis client from connection pool.
            settings: Application settings.
        """
        self.settings = settings
        self.redis = redis_client
        self.key_prefix = "job:cancel:"

    def _make_key(self, job_id: str) -> str:
        """Create Redis key for job cancellation.

        Args:
            job_id: Job UUID.

        Returns:
            Redis key string.
        """
        return f"{self.key_prefix}{job_id}"

    async def set_cancellation(self, job_id: str, reason: str | None = None) -> bool:
        """Set cancellation flag for a job.

        Args:
            job_id: Job UUID.
            reason: Optional cancellation reason.

        Returns:
            True if successful, False otherwise.
        """
        try:
            key = self._make_key(job_id)
            data = {"cancelled": True, "reason": reason}
            # Keep flag for 24 hours
            await self.redis.setex(key, 86400, json.dumps(data))
            logger.info("job_cancellation_set", job_id=job_id, reason=reason)
            return True
        except Exception as e:
            logger.error("job_cancellation_set_error", job_id=job_id, error=str(e))
            return False

    async def is_cancelled(self, job_id: str) -> bool:
        """Check if job is marked for cancellation.

        Args:
            job_id: Job UUID.

        Returns:
            True if job should be cancelled, False otherwise.
        """
        try:
            key = self._make_key(job_id)
            return bool(await self.redis.exists(key))
        except Exception as e:
            logger.error("job_cancellation_check_error", job_id=job_id, error=str(e))
            return False

    async def clear_cancellation(self, job_id: str) -> bool:
        """Clear cancellation flag for a job.

        Args:
            job_id: Job UUID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            key = self._make_key(job_id)
            await self.redis.delete(key)
            logger.info("job_cancellation_cleared", job_id=job_id)
            return True
        except Exception as e:
            logger.error("job_cancellation_clear_error", job_id=job_id, error=str(e))
            return False


class RateLimiter:
    """Redis-based rate limiter using sliding window.

    Tracks request counts per website within a time window.
    """

    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Initialize rate limiter.

        Args:
            redis_client: Redis client from connection pool.
            settings: Application settings.
        """
        self.settings = settings
        self.redis = redis_client
        self.key_prefix = "ratelimit:"

    def _make_key(self, website_id: str) -> str:
        """Create Redis key for rate limiting.

        Args:
            website_id: Website UUID.

        Returns:
            Redis key string.
        """
        return f"{self.key_prefix}{website_id}"

    async def increment(self, website_id: str) -> int:
        """Increment request counter for website.

        Args:
            website_id: Website UUID.

        Returns:
            Current request count.
        """
        try:
            key = self._make_key(website_id)
            # Increment counter
            count = await self.redis.incr(key)

            # Set expiry only on first increment
            if count == 1:
                await self.redis.expire(key, self.settings.rate_limit_period)

            return count
        except Exception as e:
            logger.error("ratelimit_increment_error", website_id=website_id, error=str(e))
            return 0

    async def is_rate_limited(self, website_id: str) -> bool:
        """Check if website has exceeded rate limit.

        Args:
            website_id: Website UUID.

        Returns:
            True if rate limited, False otherwise.
        """
        try:
            count = await self.get_count(website_id)
            is_limited = count >= self.settings.rate_limit_requests
            if is_limited:
                logger.warning("rate_limit_exceeded", website_id=website_id, count=count)
            return is_limited
        except Exception as e:
            logger.error("ratelimit_check_error", website_id=website_id, error=str(e))
            return False

    async def get_count(self, website_id: str) -> int:
        """Get current request count for website.

        Args:
            website_id: Website UUID.

        Returns:
            Current request count.
        """
        try:
            key = self._make_key(website_id)
            value: str | None = await self.redis.get(key)
            return int(value) if value else 0
        except Exception as e:
            logger.error("ratelimit_get_count_error", website_id=website_id, error=str(e))
            return 0

    async def reset(self, website_id: str) -> bool:
        """Reset rate limit counter for website.

        Args:
            website_id: Website UUID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            key = self._make_key(website_id)
            await self.redis.delete(key)
            logger.info("ratelimit_reset", website_id=website_id)
            return True
        except Exception as e:
            logger.error("ratelimit_reset_error", website_id=website_id, error=str(e))
            return False


class BrowserPoolStatus:
    """Redis-based browser pool status tracking.

    Stores current state of the browser pool for monitoring and coordination.
    """

    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Initialize browser pool status tracker.

        Args:
            redis_client: Redis client from connection pool.
            settings: Application settings.
        """
        self.settings = settings
        self.redis = redis_client
        self.key = "browser:pool:status"

    async def update_status(
        self,
        active_browsers: int,
        active_contexts: int,
        available_contexts: int,
        memory_mb: float,
    ) -> bool:
        """Update browser pool status.

        Args:
            active_browsers: Number of active browser instances.
            active_contexts: Number of active browser contexts.
            available_contexts: Number of available contexts.
            memory_mb: Memory usage in MB.

        Returns:
            True if successful, False otherwise.
        """
        try:
            status = {
                "active_browsers": active_browsers,
                "active_contexts": active_contexts,
                "available_contexts": available_contexts,
                "memory_mb": memory_mb,
            }
            # Keep status for 5 minutes
            await self.redis.setex(self.key, 300, json.dumps(status))
            logger.debug(
                "browser_pool_status_updated",
                active_browsers=active_browsers,
                active_contexts=active_contexts,
                memory_mb=memory_mb,
            )
            return True
        except Exception as e:
            logger.error("browser_pool_status_update_error", error=str(e))
            return False

    async def get_status(self) -> dict[str, Any] | None:
        """Get current browser pool status.

        Returns:
            Status dict if exists, None otherwise.
        """
        try:
            value: str | None = await self.redis.get(self.key)
            if value:
                return cast(dict[str, Any], json.loads(value))
            return None
        except Exception as e:
            logger.error("browser_pool_status_get_error", error=str(e))
            return None


class JobProgressCache:
    """Redis-based job progress caching.

    Stores temporary progress updates for running jobs.
    Progress data is updated frequently and has a short TTL.
    """

    def __init__(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Initialize job progress cache.

        Args:
            redis_client: Redis client from connection pool.
            settings: Application settings.
        """
        self.settings = settings
        self.redis = redis_client
        self.key_prefix = "job:progress:"

    def _make_key(self, job_id: str) -> str:
        """Create Redis key for job progress.

        Args:
            job_id: Job UUID.

        Returns:
            Redis key string.
        """
        return f"{self.key_prefix}{job_id}"

    async def set_progress(self, job_id: str, progress: dict[str, Any]) -> bool:
        """Set progress data for a job.

        Args:
            job_id: Job UUID.
            progress: Progress data dict (pages_crawled, pages_pending, etc.).

        Returns:
            True if successful, False otherwise.
        """
        try:
            key = self._make_key(job_id)
            # Cache progress for 1 hour
            await self.redis.setex(key, 3600, json.dumps(progress))
            logger.debug("job_progress_set", job_id=job_id)
            return True
        except Exception as e:
            logger.error("job_progress_set_error", job_id=job_id, error=str(e))
            return False

    async def get_progress(self, job_id: str) -> dict[str, Any] | None:
        """Get progress data for a job.

        Args:
            job_id: Job UUID.

        Returns:
            Progress data if exists, None otherwise.
        """
        try:
            key = self._make_key(job_id)
            value: str | None = await self.redis.get(key)
            if value:
                return cast(dict[str, Any], json.loads(value))
            return None
        except Exception as e:
            logger.error("job_progress_get_error", job_id=job_id, error=str(e))
            return None

    async def delete_progress(self, job_id: str) -> bool:
        """Delete progress data for a job.

        Args:
            job_id: Job UUID.

        Returns:
            True if successful, False otherwise.
        """
        try:
            key = self._make_key(job_id)
            await self.redis.delete(key)
            logger.debug("job_progress_deleted", job_id=job_id)
            return True
        except Exception as e:
            logger.error("job_progress_delete_error", job_id=job_id, error=str(e))
            return False
