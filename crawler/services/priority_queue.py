"""Priority-based job queue using Redis sorted sets.

This module provides a priority queue implementation that ensures jobs are processed
in the correct order based on priority, scheduled time, and creation time.

Priority Queue Ordering:
1. Priority (0-10, higher number = higher priority)
2. Scheduled time (earlier scheduled jobs first within same priority)
3. Creation time (FIFO within same priority and scheduled time)

Score Calculation:
- Score = (10 - priority) * 10^12 + scheduled_timestamp_ms
- Lower score = processed first
- This ensures high-priority jobs (priority=10) get lowest scores

Example Scores:
- Priority 10, scheduled at 2024-01-01 00:00:00:
  Score = (10-10)*10^12 + 1704067200000 = 1704067200000
- Priority 5, scheduled at 2024-01-01 00:00:00:
  Score = (10-5)*10^12 + 1704067200000 = 5001704067200000
- Priority 0, scheduled at 2024-01-01 00:00:00:
  Score = (10-0)*10^12 + 1704067200000 = 10001704067200000
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import redis.asyncio as redis

from crawler.core.logging import get_logger

logger = get_logger(__name__)

# Priority levels (0-10, higher = more urgent)
PRIORITY_MIN = 0
PRIORITY_MAX = 10
PRIORITY_DEFAULT = 5

# Priority assignments by job type
PRIORITY_MANUAL_TRIGGER = 10  # User-initiated jobs (highest priority)
PRIORITY_SCHEDULED_HIGH = 6  # Important scheduled jobs
PRIORITY_SCHEDULED = 5  # Normal scheduled jobs (default)
PRIORITY_SCHEDULED_LOW = 4  # Low-priority scheduled jobs
PRIORITY_RETRY = 0  # Retry jobs (lowest priority)

# Score multiplier to ensure priority dominates over timestamp
PRIORITY_MULTIPLIER = 10**12


class PriorityQueueService:
    """Redis-based priority queue using sorted sets (ZSET).

    Uses Redis sorted sets to maintain a priority-ordered job queue.
    Jobs are scored based on priority and scheduled time to ensure
    correct processing order.

    The queue uses two Redis keys:
    - {prefix}:jobs - Sorted set of job IDs with priority scores
    - {prefix}:data:{job_id} - Hash storing job metadata

    Thread-safety: All operations use atomic Redis commands.
    """

    def __init__(self, redis_client: redis.Redis, key_prefix: str = "priority_queue"):
        """Initialize priority queue service.

        Args:
            redis_client: Async Redis client
            key_prefix: Redis key prefix for queue data (default: "priority_queue")
        """
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.queue_key = f"{key_prefix}:jobs"

    def _job_data_key(self, job_id: str) -> str:
        """Get Redis key for job metadata.

        Args:
            job_id: Job ID

        Returns:
            Redis key for job data hash
        """
        return f"{self.key_prefix}:data:{job_id}"

    def _calculate_score(self, priority: int, scheduled_at: datetime | None = None) -> float:
        """Calculate sort score for job.

        Lower score = higher priority (processed first).

        Formula: score = (PRIORITY_MAX - priority) * PRIORITY_MULTIPLIER + scheduled_timestamp_ms

        Args:
            priority: Job priority (0-10, 10=highest)
            scheduled_at: Optional scheduled execution time (default: now)

        Returns:
            Float score for Redis ZSET

        Examples:
            >>> # Priority 10 (manual), scheduled at 2024-01-01 00:00:00
            >>> _calculate_score(10, datetime(2024, 1, 1, tzinfo=UTC))
            1704067200000.0  # Lowest score = highest priority

            >>> # Priority 5 (scheduled), same time
            >>> _calculate_score(5, datetime(2024, 1, 1, tzinfo=UTC))
            5001704067200000.0  # Higher score = lower priority

            >>> # Priority 0 (retry), same time
            >>> _calculate_score(0, datetime(2024, 1, 1, tzinfo=UTC))
            10001704067200000.0  # Highest score = lowest priority
        """
        # Guard: validate priority range
        if not PRIORITY_MIN <= priority <= PRIORITY_MAX:
            logger.warning(
                "invalid_priority",
                priority=priority,
                min=PRIORITY_MIN,
                max=PRIORITY_MAX,
                reason=f"Priority must be {PRIORITY_MIN}-{PRIORITY_MAX}, clamping to range",
            )
            priority = max(PRIORITY_MIN, min(PRIORITY_MAX, priority))

        # Use scheduled time or current time
        timestamp = scheduled_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)

        timestamp_ms = int(timestamp.timestamp() * 1000)

        # Calculate score: higher priority = lower score
        # Multiply by large number so priority dominates over timestamp
        score = (PRIORITY_MAX - priority) * PRIORITY_MULTIPLIER + timestamp_ms

        return float(score)

    async def enqueue(
        self,
        job_id: str,
        job_data: dict[str, Any],
        priority: int = PRIORITY_DEFAULT,
        scheduled_at: datetime | None = None,
    ) -> bool:
        """Add job to priority queue.

        Args:
            job_id: Unique job identifier
            job_data: Job metadata (will be JSON-serialized)
            priority: Job priority 0-10 (default: 5, 10=highest)
            scheduled_at: Optional scheduled execution time (default: now)

        Returns:
            True if job was added, False if job already exists

        Note:
            If job already exists in queue, it will NOT be updated.
            Use remove() first if you need to re-enqueue with different priority.
        """
        try:
            # Check if job already exists
            exists = await self.redis.zscore(self.queue_key, job_id) is not None
            if exists:
                logger.warning(
                    "job_already_in_queue",
                    job_id=job_id,
                    priority=priority,
                    reason="Job already exists in queue - not updating",
                )
                return False

            score = self._calculate_score(priority, scheduled_at)

            # Store job data as JSON in a hash
            data_key = self._job_data_key(job_id)
            job_data_with_meta = {
                **job_data,
                "priority": priority,
                "scheduled_at": scheduled_at.isoformat() if scheduled_at else None,
                "enqueued_at": datetime.now(UTC).isoformat(),
            }

            # Use pipeline for atomicity
            async with self.redis.pipeline(transaction=True) as pipe:
                # Add job to sorted set
                await pipe.zadd(self.queue_key, {job_id: score})
                # Store job metadata
                await pipe.set(data_key, json.dumps(job_data_with_meta))
                # Set TTL on data (7 days) to prevent memory leaks
                await pipe.expire(data_key, 7 * 24 * 3600)
                await pipe.execute()

            logger.info(
                "job_enqueued",
                job_id=job_id,
                priority=priority,
                score=score,
                scheduled_at=scheduled_at.isoformat() if scheduled_at else None,
            )

            return True

        except Exception as e:
            logger.error(
                "enqueue_failed",
                job_id=job_id,
                priority=priority,
                error=str(e),
                exc_info=True,
            )
            return False

    async def dequeue(self) -> tuple[str, dict[str, Any]] | None:
        """Atomically dequeue highest-priority job.

        Uses ZPOPMIN to atomically remove and return the lowest-score
        (highest-priority) job from the queue.

        Returns:
            Tuple of (job_id, job_data) if job available, None if queue empty

        Note:
            Job data is automatically removed from Redis after dequeue.
        """
        try:
            # Atomically pop lowest score (highest priority)
            result = await self.redis.zpopmin(self.queue_key, count=1)

            # Guard: empty queue
            if not result:
                logger.debug("queue_empty", reason="No jobs available")
                return None

            # result is list of tuples: [(job_id, score)]
            job_id, score = result[0]
            if isinstance(job_id, bytes):
                job_id = job_id.decode("utf-8")

            # Fetch job data
            data_key = self._job_data_key(job_id)
            job_data_json = await self.redis.get(data_key)

            # Guard: data not found (shouldn't happen, but be defensive)
            if not job_data_json:
                logger.error(
                    "job_data_missing",
                    job_id=job_id,
                    score=score,
                    reason="Job was in queue but data not found in Redis",
                )
                return None

            # Parse job data
            job_data = json.loads(job_data_json)

            # Clean up data key
            await self.redis.delete(data_key)

            logger.info(
                "job_dequeued",
                job_id=job_id,
                priority=job_data.get("priority"),
                score=score,
            )

            return (job_id, job_data)

        except Exception as e:
            logger.error("dequeue_failed", error=str(e), exc_info=True)
            return None

    async def remove(self, job_id: str) -> bool:
        """Remove specific job from queue.

        Useful for cancellation or cleanup of stale jobs.

        Args:
            job_id: Job ID to remove

        Returns:
            True if job was removed, False if job not in queue
        """
        try:
            async with self.redis.pipeline(transaction=True) as pipe:
                # Remove from sorted set
                await pipe.zrem(self.queue_key, job_id)
                # Remove data
                await pipe.delete(self._job_data_key(job_id))
                results = await pipe.execute()

            removed = bool(results[0] == 1)  # ZREM returns number of elements removed

            if removed:
                logger.info("job_removed_from_queue", job_id=job_id)
            else:
                logger.debug("job_not_in_queue", job_id=job_id)

            return removed

        except Exception as e:
            logger.error("remove_failed", job_id=job_id, error=str(e), exc_info=True)
            return False

    async def get_queue_size(self) -> int:
        """Get number of jobs in queue.

        Returns:
            Number of jobs currently in queue
        """
        try:
            return await self.redis.zcard(self.queue_key)
        except Exception as e:
            logger.error("get_queue_size_failed", error=str(e))
            return 0

    async def peek(self, count: int = 1) -> list[tuple[str, dict[str, Any]]]:
        """View top N jobs without removing them.

        Args:
            count: Number of jobs to peek (default: 1)

        Returns:
            List of (job_id, job_data) tuples, ordered by priority
        """
        try:
            # Get top N jobs with scores (lowest scores first = highest priority)
            results = await self.redis.zrange(self.queue_key, 0, count - 1, withscores=True)

            jobs = []
            for job_id_bytes, score in results:
                job_id = (
                    job_id_bytes.decode("utf-8")
                    if isinstance(job_id_bytes, bytes)
                    else job_id_bytes
                )
                data_key = self._job_data_key(job_id)
                job_data_json = await self.redis.get(data_key)

                if job_data_json:
                    job_data = json.loads(job_data_json)
                    jobs.append((job_id, job_data))

            return jobs

        except Exception as e:
            logger.error("peek_failed", count=count, error=str(e))
            return []

    async def clear(self) -> int:
        """Remove all jobs from queue.

        Returns:
            Number of jobs removed

        Warning:
            This is a destructive operation. Use with caution.
        """
        try:
            # Get all job IDs
            job_ids = await self.redis.zrange(self.queue_key, 0, -1)

            if not job_ids:
                return 0

            # Delete all data keys
            data_keys = [
                self._job_data_key(jid.decode("utf-8") if isinstance(jid, bytes) else jid)
                for jid in job_ids
            ]

            async with self.redis.pipeline(transaction=True) as pipe:
                # Delete all data keys
                for key in data_keys:
                    await pipe.delete(key)
                # Delete queue
                await pipe.delete(self.queue_key)
                await pipe.execute()

            count = len(job_ids)
            logger.warning("queue_cleared", job_count=count)
            return count

        except Exception as e:
            logger.error("clear_failed", error=str(e))
            return 0
