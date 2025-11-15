"""Redis-based retry scheduler cache using sorted sets for efficient scheduling.

This service uses Redis sorted sets (ZSET) to schedule delayed job retries without
blocking worker threads. The timestamp is used as the score, allowing efficient
retrieval of jobs ready for retry.
"""

from datetime import datetime

from redis.asyncio import Redis

from config import Settings
from crawler.core.logging import get_logger

logger = get_logger(__name__)


class RetrySchedulerCache:
    """Redis-based cache for scheduling delayed job retries.

    Uses Redis sorted sets where:
    - Member: job_id (string)
    - Score: Unix timestamp when job should be retried

    This allows O(log N) insertion and O(log N + M) retrieval of ready jobs,
    where M is the number of jobs ready for retry.
    """

    def __init__(self, redis: Redis, settings: Settings):
        """Initialize retry scheduler cache.

        Args:
            redis: Async Redis client
            settings: Application settings
        """
        self.redis = redis
        self.settings = settings
        self.key = "retry:schedule"

    async def schedule_retry(self, job_id: str, retry_at: datetime) -> bool:
        """Schedule a job for retry at a specific time.

        Args:
            job_id: Job UUID to schedule
            retry_at: When the job should be retried

        Returns:
            True if scheduled successfully
        """
        try:
            timestamp = retry_at.timestamp()
            await self.redis.zadd(self.key, {job_id: timestamp})
            logger.debug(
                "retry_scheduled",
                job_id=job_id,
                retry_at=retry_at.isoformat(),
                timestamp=timestamp,
            )
            return True
        except Exception as e:
            logger.error(
                "failed_to_schedule_retry",
                job_id=job_id,
                error=str(e),
                exc_info=True,
            )
            return False

    async def get_ready_jobs(self, limit: int = 100) -> list[str]:
        """Get jobs ready for retry (scheduled time <= now).

        Args:
            limit: Maximum number of jobs to return

        Returns:
            List of job IDs ready for retry (oldest first)
        """
        try:
            now = datetime.now().timestamp()
            # ZRANGEBYSCORE returns jobs with score from 0 to now (inclusive)
            # LIMIT 0 <limit> returns first <limit> results
            job_ids = await self.redis.zrangebyscore(
                self.key,
                min=0,
                max=now,
                start=0,
                num=limit,
            )
            # Convert bytes to strings
            return [
                job_id.decode("utf-8") if isinstance(job_id, bytes) else job_id
                for job_id in job_ids
            ]
        except Exception as e:
            logger.error(
                "failed_to_get_ready_jobs",
                error=str(e),
                exc_info=True,
            )
            return []

    async def remove_scheduled(self, job_id: str) -> bool:
        """Remove a job from the retry schedule.

        Called after successfully enqueueing the job or if the job is cancelled.

        Args:
            job_id: Job UUID to remove

        Returns:
            True if removed successfully
        """
        try:
            removed = await self.redis.zrem(self.key, job_id)
            if removed:
                logger.debug("retry_schedule_removed", job_id=job_id)
            return bool(removed)
        except Exception as e:
            logger.error(
                "failed_to_remove_scheduled",
                job_id=job_id,
                error=str(e),
                exc_info=True,
            )
            return False

    async def get_scheduled_time(self, job_id: str) -> datetime | None:
        """Get the scheduled retry time for a job.

        Args:
            job_id: Job UUID

        Returns:
            Scheduled retry time or None if not scheduled
        """
        try:
            timestamp = await self.redis.zscore(self.key, job_id)
            if timestamp is None:
                return None
            return datetime.fromtimestamp(timestamp)
        except Exception as e:
            logger.error(
                "failed_to_get_scheduled_time",
                job_id=job_id,
                error=str(e),
                exc_info=True,
            )
            return None

    async def count_scheduled(self) -> int:
        """Get total number of scheduled retries.

        Returns:
            Number of jobs in the retry schedule
        """
        try:
            return await self.redis.zcard(self.key)
        except Exception as e:
            logger.error(
                "failed_to_count_scheduled",
                error=str(e),
                exc_info=True,
            )
            return 0

    async def clear_all(self) -> bool:
        """Clear all scheduled retries (for testing/maintenance).

        Returns:
            True if cleared successfully
        """
        try:
            await self.redis.delete(self.key)
            logger.info("retry_schedule_cleared")
            return True
        except Exception as e:
            logger.error(
                "failed_to_clear_schedule",
                error=str(e),
                exc_info=True,
            )
            return False
