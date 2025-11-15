"""Integration tests for Redis-based retry scheduler."""

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
import redis.asyncio as redis

from config import get_settings
from crawler.services.nats_queue import NATSQueueService
from crawler.services.retry_scheduler import (
    retry_scheduler_loop,
    start_retry_scheduler,
    stop_retry_scheduler,
)
from crawler.services.retry_scheduler_cache import RetrySchedulerCache


@pytest.fixture
async def redis_client():
    """Create Redis client for testing."""
    settings = get_settings()
    client = redis.from_url(settings.redis_url, decode_responses=True)
    yield client
    # Cleanup: flush test data
    await client.flushdb()
    await client.aclose()


@pytest.fixture
async def retry_cache(redis_client: redis.Redis) -> RetrySchedulerCache:
    """Create retry scheduler cache."""
    settings = get_settings()
    cache = RetrySchedulerCache(redis_client, settings)
    # Cleanup before and after tests
    await redis_client.delete(cache.key)
    yield cache
    await redis_client.delete(cache.key)


@pytest.fixture
async def mock_nats_queue() -> NATSQueueService:
    """Create mock NATS queue service."""
    mock = AsyncMock(spec=NATSQueueService)
    mock.publish_job = AsyncMock(return_value=True)
    return mock


# ============================================================================
# RetrySchedulerCache Tests
# ============================================================================


class TestRetrySchedulerCache:
    """Test Redis ZSET-based retry scheduling cache."""

    async def test_schedule_retry_adds_to_redis(self, retry_cache: RetrySchedulerCache):
        """Scheduling a retry should add job to Redis ZSET."""
        job_id = "test-job-123"
        retry_at = datetime.now(UTC) + timedelta(seconds=60)

        success = await retry_cache.schedule_retry(job_id, retry_at)

        assert success is True

        # Verify job exists in Redis with correct timestamp
        score = await retry_cache.redis.zscore(retry_cache.key, job_id)
        assert score is not None
        # Score should be Unix timestamp
        expected_score = retry_at.timestamp()
        assert abs(float(score) - expected_score) < 1.0  # Allow 1s tolerance

    async def test_get_ready_jobs_returns_due_jobs(self, retry_cache: RetrySchedulerCache):
        """get_ready_jobs should return jobs with retry_at <= now."""
        now = datetime.now(UTC)

        # Schedule 3 jobs:
        # 1. Past (ready)
        # 2. Far future (not ready)
        # 3. Just past (ready)
        await retry_cache.schedule_retry("job-past", now - timedelta(seconds=30))
        await retry_cache.schedule_retry("job-future", now + timedelta(seconds=300))
        await retry_cache.schedule_retry("job-ready", now - timedelta(seconds=5))

        ready_jobs = await retry_cache.get_ready_jobs(limit=10)

        # Should return 2 ready jobs
        assert len(ready_jobs) == 2
        assert set(ready_jobs) == {"job-past", "job-ready"}

    async def test_get_ready_jobs_respects_limit(self, retry_cache: RetrySchedulerCache):
        """get_ready_jobs should respect the limit parameter."""
        now = datetime.now(UTC)

        # Schedule 5 ready jobs
        for i in range(5):
            await retry_cache.schedule_retry(f"job-{i}", now - timedelta(seconds=i))

        # Request only 3
        ready_jobs = await retry_cache.get_ready_jobs(limit=3)

        assert len(ready_jobs) == 3

    async def test_get_ready_jobs_oldest_first(self, retry_cache: RetrySchedulerCache):
        """get_ready_jobs should return oldest jobs first (FIFO)."""
        now = datetime.now(UTC)

        # Schedule in reverse chronological order
        await retry_cache.schedule_retry("job-3", now - timedelta(seconds=10))
        await retry_cache.schedule_retry("job-2", now - timedelta(seconds=20))
        await retry_cache.schedule_retry("job-1", now - timedelta(seconds=30))

        ready_jobs = await retry_cache.get_ready_jobs(limit=10)

        # Should return oldest first
        assert ready_jobs == ["job-1", "job-2", "job-3"]

    async def test_remove_scheduled_deletes_job(self, retry_cache: RetrySchedulerCache):
        """remove_scheduled should delete job from Redis ZSET."""
        job_id = "test-job-456"
        retry_at = datetime.now(UTC) + timedelta(seconds=60)

        # Schedule job
        await retry_cache.schedule_retry(job_id, retry_at)
        assert await retry_cache.redis.zscore(retry_cache.key, job_id) is not None

        # Remove job
        removed = await retry_cache.remove_scheduled(job_id)
        assert removed is True

        # Verify job no longer exists
        assert await retry_cache.redis.zscore(retry_cache.key, job_id) is None

    async def test_remove_nonexistent_job_returns_false(self, retry_cache: RetrySchedulerCache):
        """Removing a non-existent job should return False."""
        removed = await retry_cache.remove_scheduled("nonexistent-job")
        assert removed is False

    async def test_multiple_jobs_same_timestamp(self, retry_cache: RetrySchedulerCache):
        """Multiple jobs with same retry_at should all be retrieved."""
        now = datetime.now(UTC)
        retry_at = now - timedelta(seconds=10)

        # Schedule 3 jobs at exact same time
        await retry_cache.schedule_retry("job-1", retry_at)
        await retry_cache.schedule_retry("job-2", retry_at)
        await retry_cache.schedule_retry("job-3", retry_at)

        ready_jobs = await retry_cache.get_ready_jobs(limit=10)

        # All 3 should be ready
        assert len(ready_jobs) == 3
        assert set(ready_jobs) == {"job-1", "job-2", "job-3"}


# ============================================================================
# Retry Scheduler Loop Tests
# ============================================================================


class TestRetrySchedulerLoop:
    """Test the background scheduler loop."""

    async def test_scheduler_enqueues_ready_jobs(
        self, retry_cache: RetrySchedulerCache, mock_nats_queue: NATSQueueService
    ):
        """Scheduler should enqueue jobs whose retry time has arrived."""
        now = datetime.now(UTC)

        # Schedule 2 ready jobs
        await retry_cache.schedule_retry("job-1", now - timedelta(seconds=10))
        await retry_cache.schedule_retry("job-2", now - timedelta(seconds=5))

        # Run one iteration
        task = asyncio.create_task(
            retry_scheduler_loop(retry_cache, mock_nats_queue, interval_seconds=1, batch_size=10)
        )

        # Let it run for 1.5 seconds (enough for one iteration)
        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Verify both jobs were published
        assert mock_nats_queue.publish_job.call_count == 2
        published_jobs = {call.args[0] for call in mock_nats_queue.publish_job.call_args_list}
        assert published_jobs == {"job-1", "job-2"}

    async def test_scheduler_removes_enqueued_jobs(
        self, retry_cache: RetrySchedulerCache, mock_nats_queue: NATSQueueService
    ):
        """Jobs should be removed from Redis after successful enqueue."""
        now = datetime.now(UTC)
        job_id = "job-123"

        await retry_cache.schedule_retry(job_id, now - timedelta(seconds=10))

        # Run scheduler
        task = asyncio.create_task(
            retry_scheduler_loop(retry_cache, mock_nats_queue, interval_seconds=1, batch_size=10)
        )

        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Job should be removed from Redis
        assert await retry_cache.redis.zscore(retry_cache.key, job_id) is None

    async def test_scheduler_retries_failed_publish(
        self, retry_cache: RetrySchedulerCache, mock_nats_queue: NATSQueueService
    ):
        """Failed publish should leave job in Redis for retry."""
        now = datetime.now(UTC)
        job_id = "job-failed"

        await retry_cache.schedule_retry(job_id, now - timedelta(seconds=10))

        # Mock NATS to fail
        mock_nats_queue.publish_job.return_value = False

        # Run scheduler
        task = asyncio.create_task(
            retry_scheduler_loop(retry_cache, mock_nats_queue, interval_seconds=1, batch_size=10)
        )

        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Job should still be in Redis
        assert await retry_cache.redis.zscore(retry_cache.key, job_id) is not None

    async def test_scheduler_respects_batch_size(
        self, retry_cache: RetrySchedulerCache, mock_nats_queue: NATSQueueService
    ):
        """Scheduler should process at most batch_size jobs per iteration."""
        now = datetime.now(UTC)

        # Schedule 10 ready jobs
        for i in range(10):
            await retry_cache.schedule_retry(f"job-{i}", now - timedelta(seconds=i))

        # Run with batch_size=5
        task = asyncio.create_task(
            retry_scheduler_loop(retry_cache, mock_nats_queue, interval_seconds=5, batch_size=5)
        )

        # Run for 0.5 seconds (less than interval, only one iteration)
        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Should only process 5 jobs in first iteration
        assert mock_nats_queue.publish_job.call_count == 5

        # Remaining 5 jobs should still be in Redis
        remaining = await retry_cache.get_ready_jobs(limit=10)
        assert len(remaining) == 5

    async def test_scheduler_ignores_future_jobs(
        self, retry_cache: RetrySchedulerCache, mock_nats_queue: NATSQueueService
    ):
        """Scheduler should not enqueue jobs with future retry_at."""
        now = datetime.now(UTC)

        # Schedule 1 ready, 1 future
        await retry_cache.schedule_retry("job-ready", now - timedelta(seconds=10))
        await retry_cache.schedule_retry("job-future", now + timedelta(seconds=300))

        # Run scheduler
        task = asyncio.create_task(
            retry_scheduler_loop(retry_cache, mock_nats_queue, interval_seconds=1, batch_size=10)
        )

        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Only ready job should be published
        assert mock_nats_queue.publish_job.call_count == 1
        mock_nats_queue.publish_job.assert_called_with("job-ready", {"job_id": "job-ready"})

        # Future job should remain in Redis
        assert await retry_cache.redis.zscore(retry_cache.key, "job-future") is not None

    async def test_scheduler_continues_after_exception(
        self, retry_cache: RetrySchedulerCache, mock_nats_queue: NATSQueueService
    ):
        """Scheduler should continue running after exception in one job."""
        now = datetime.now(UTC)

        await retry_cache.schedule_retry("job-1", now - timedelta(seconds=10))
        await retry_cache.schedule_retry("job-2", now - timedelta(seconds=5))

        # Track calls
        call_count = 0

        async def mock_publish(job_id, _):
            nonlocal call_count
            call_count += 1
            if job_id == "job-1":
                raise RuntimeError("NATS error")
            return True

        mock_nats_queue.publish_job.side_effect = mock_publish

        # Run scheduler for short duration (one iteration)
        task = asyncio.create_task(
            retry_scheduler_loop(retry_cache, mock_nats_queue, interval_seconds=5, batch_size=10)
        )

        await asyncio.sleep(0.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # Both jobs should be attempted in one iteration
        assert call_count == 2

        # Job-1 should remain (exception), job-2 should be removed (success)
        assert await retry_cache.redis.zscore(retry_cache.key, "job-1") is not None
        assert await retry_cache.redis.zscore(retry_cache.key, "job-2") is None


# ============================================================================
# Scheduler Lifecycle Tests
# ============================================================================


class TestSchedulerLifecycle:
    """Test starting and stopping the scheduler service."""

    async def test_start_creates_background_task(self):
        """start_retry_scheduler should create background task."""
        retry_cache = MagicMock(spec=RetrySchedulerCache)
        nats_queue = MagicMock(spec=NATSQueueService)

        await start_retry_scheduler(retry_cache, nats_queue, interval_seconds=1, batch_size=10)

        # Task should be created
        from crawler.services.retry_scheduler import _scheduler_task

        assert _scheduler_task is not None
        assert not _scheduler_task.done()

        # Cleanup
        await stop_retry_scheduler()

    async def test_stop_cancels_background_task(self):
        """stop_retry_scheduler should cancel and cleanup task."""
        retry_cache = MagicMock(spec=RetrySchedulerCache)
        nats_queue = MagicMock(spec=NATSQueueService)

        await start_retry_scheduler(retry_cache, nats_queue, interval_seconds=1, batch_size=10)

        # Stop scheduler
        await stop_retry_scheduler()

        # Task should be cancelled and cleaned up
        from crawler.services.retry_scheduler import _scheduler_task

        assert _scheduler_task is None

    async def test_start_twice_does_not_create_duplicate(self):
        """Starting scheduler twice should not create duplicate tasks."""
        retry_cache = MagicMock(spec=RetrySchedulerCache)
        nats_queue = MagicMock(spec=NATSQueueService)

        await start_retry_scheduler(retry_cache, nats_queue)

        from crawler.services.retry_scheduler import _scheduler_task

        first_task = _scheduler_task

        # Try starting again
        await start_retry_scheduler(retry_cache, nats_queue)

        # Should be same task
        assert _scheduler_task is first_task

        # Cleanup
        await stop_retry_scheduler()

    async def test_stop_without_start_is_safe(self):
        """Stopping scheduler when not running should not raise error."""
        # Ensure no scheduler is running
        from crawler.services.retry_scheduler import _scheduler_task

        if _scheduler_task is not None:
            await stop_retry_scheduler()

        # Should not raise
        await stop_retry_scheduler()


# ============================================================================
# Performance Tests
# ============================================================================


class TestSchedulerPerformance:
    """Test scheduler performance with realistic workloads."""

    async def test_large_batch_processing(
        self, retry_cache: RetrySchedulerCache, mock_nats_queue: NATSQueueService
    ):
        """Scheduler should efficiently handle large batches."""
        now = datetime.now(UTC)

        # Schedule 100 ready jobs
        for i in range(100):
            await retry_cache.schedule_retry(f"job-{i:03d}", now - timedelta(seconds=i))

        # Run scheduler with batch_size=100
        task = asyncio.create_task(
            retry_scheduler_loop(retry_cache, mock_nats_queue, interval_seconds=1, batch_size=100)
        )

        await asyncio.sleep(1.5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        # All 100 jobs should be processed
        assert mock_nats_queue.publish_job.call_count == 100

        # Redis should be empty
        remaining = await retry_cache.get_ready_jobs(limit=200)
        assert len(remaining) == 0
