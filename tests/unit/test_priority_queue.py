"""Unit tests for PriorityQueueService."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from crawler.services.priority_queue import (
    PRIORITY_DEFAULT,
    PRIORITY_MANUAL_TRIGGER,
    PRIORITY_MAX,
    PRIORITY_MIN,
    PRIORITY_MULTIPLIER,
    PRIORITY_RETRY,
    PRIORITY_SCHEDULED,
    PRIORITY_SCHEDULED_HIGH,
    PRIORITY_SCHEDULED_LOW,
    PriorityQueueService,
)


@pytest.fixture
def mock_redis():
    """Create mock Redis client."""
    redis_mock = AsyncMock()
    redis_mock.pipeline = MagicMock()
    return redis_mock


@pytest.fixture
def priority_queue(mock_redis):
    """Create priority queue service with mock Redis."""
    return PriorityQueueService(redis_client=mock_redis, key_prefix="test_queue")


class TestPriorityConstants:
    """Test priority level constants."""

    def test_priority_range(self):
        """Test priority constants are within valid range."""
        assert PRIORITY_MIN == 0
        assert PRIORITY_MAX == 10
        assert PRIORITY_MIN <= PRIORITY_DEFAULT <= PRIORITY_MAX

    def test_priority_assignments(self):
        """Test priority assignments for different job types."""
        # Manual trigger should be highest priority
        assert PRIORITY_MANUAL_TRIGGER == 10
        assert PRIORITY_MANUAL_TRIGGER == PRIORITY_MAX

        # Scheduled jobs should be mid-range (4-6)
        assert 4 <= PRIORITY_SCHEDULED_LOW <= 6
        assert 4 <= PRIORITY_SCHEDULED <= 6
        assert 4 <= PRIORITY_SCHEDULED_HIGH <= 6

        # Retry should be lowest priority
        assert PRIORITY_RETRY == 0
        assert PRIORITY_RETRY == PRIORITY_MIN

    def test_priority_ordering(self):
        """Test priority constants are in correct order."""
        assert PRIORITY_MANUAL_TRIGGER > PRIORITY_SCHEDULED_HIGH
        assert PRIORITY_SCHEDULED_HIGH > PRIORITY_SCHEDULED
        assert PRIORITY_SCHEDULED > PRIORITY_SCHEDULED_LOW
        assert PRIORITY_SCHEDULED_LOW > PRIORITY_RETRY


class TestScoreCalculation:
    """Test priority score calculation logic."""

    def test_score_calculation_basic(self, priority_queue):
        """Test basic score calculation."""
        # Fixed timestamp for deterministic testing
        timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        timestamp_ms = int(timestamp.timestamp() * 1000)

        # Priority 10 (highest) should have lowest score
        score_p10 = priority_queue._calculate_score(10, timestamp)
        expected_p10 = (10 - 10) * PRIORITY_MULTIPLIER + timestamp_ms
        assert score_p10 == expected_p10
        assert score_p10 == timestamp_ms  # Should be just timestamp for max priority

        # Priority 5 (default) should have higher score
        score_p5 = priority_queue._calculate_score(5, timestamp)
        expected_p5 = (10 - 5) * PRIORITY_MULTIPLIER + timestamp_ms
        assert score_p5 == expected_p5

        # Priority 0 (lowest) should have highest score
        score_p0 = priority_queue._calculate_score(0, timestamp)
        expected_p0 = (10 - 0) * PRIORITY_MULTIPLIER + timestamp_ms
        assert score_p0 == expected_p0

    def test_score_ordering_by_priority(self, priority_queue):
        """Test that higher priority gets lower score."""
        timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        score_p10 = priority_queue._calculate_score(10, timestamp)
        score_p5 = priority_queue._calculate_score(5, timestamp)
        score_p0 = priority_queue._calculate_score(0, timestamp)

        # Lower score = higher priority (processed first)
        assert score_p10 < score_p5 < score_p0

    def test_score_ordering_by_time(self, priority_queue):
        """Test that within same priority, earlier time gets lower score."""
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        later_time = base_time + timedelta(hours=1)

        score_early = priority_queue._calculate_score(5, base_time)
        score_late = priority_queue._calculate_score(5, later_time)

        # Earlier time should have lower score (processed first)
        assert score_early < score_late

    def test_score_priority_dominates_time(self, priority_queue):
        """Test that priority dominates over timestamp."""
        # High priority job scheduled much later
        high_priority_late = datetime(2024, 12, 31, 23, 59, 59, tzinfo=UTC)
        # Low priority job scheduled much earlier
        low_priority_early = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        score_high_late = priority_queue._calculate_score(10, high_priority_late)
        score_low_early = priority_queue._calculate_score(0, low_priority_early)

        # High priority should still have lower score despite being scheduled later
        assert score_high_late < score_low_early

    def test_score_invalid_priority_clamped(self, priority_queue):
        """Test that invalid priority values are clamped to valid range."""
        timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Priority too high (should clamp to 10)
        score_too_high = priority_queue._calculate_score(15, timestamp)
        score_max = priority_queue._calculate_score(10, timestamp)
        assert score_too_high == score_max

        # Priority too low (should clamp to 0)
        score_too_low = priority_queue._calculate_score(-5, timestamp)
        score_min = priority_queue._calculate_score(0, timestamp)
        assert score_too_low == score_min

    def test_score_default_timestamp(self, priority_queue):
        """Test that score calculation defaults to current time if timestamp not provided."""
        score = priority_queue._calculate_score(5, scheduled_at=None)
        # Score should be a positive number
        assert score > 0
        # Score should include priority component
        assert score > PRIORITY_MULTIPLIER  # For priority 5: (10-5)*10^12

    def test_score_naive_timestamp_converted(self, priority_queue):
        """Test that naive datetime is converted to UTC."""
        # Naive datetime (no timezone)
        naive_time = datetime(2024, 1, 1, 0, 0, 0)
        score = priority_queue._calculate_score(5, naive_time)

        # Should not raise error and should return valid score
        assert score > 0


class TestEnqueue:
    """Test job enqueuing functionality."""

    @pytest.mark.asyncio
    async def test_enqueue_success(self, priority_queue, mock_redis):
        """Test successfully enqueuing a job."""
        # Setup mock pipeline
        pipeline_mock = AsyncMock()
        pipeline_mock.zadd = AsyncMock()
        pipeline_mock.set = AsyncMock()
        pipeline_mock.expire = AsyncMock()
        pipeline_mock.execute = AsyncMock(
            return_value=[1, True, True]
        )  # ZADD added 1, SET ok, EXPIRE ok
        pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
        pipeline_mock.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = pipeline_mock

        job_id = "test-job-123"
        job_data = {"website_id": "site-1", "seed_url": "https://example.com"}
        timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        result = await priority_queue.enqueue(
            job_id=job_id, job_data=job_data, priority=5, scheduled_at=timestamp
        )

        assert result is True
        # Verify ZADD was called with correct score
        pipeline_mock.zadd.assert_called_once()
        # Verify job data was stored
        pipeline_mock.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_enqueue_duplicate_job(self, priority_queue, mock_redis):
        """Test enqueuing a job that already exists."""
        # Setup mock pipeline - ZADD returns 0 for duplicate
        pipeline_mock = AsyncMock()
        pipeline_mock.zadd = AsyncMock()
        pipeline_mock.set = AsyncMock()
        pipeline_mock.expire = AsyncMock()
        pipeline_mock.execute = AsyncMock(return_value=[0, True, True])  # ZADD added 0 (duplicate)
        pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
        pipeline_mock.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = pipeline_mock

        job_id = "duplicate-job"
        job_data = {"test": "data"}

        result = await priority_queue.enqueue(job_id=job_id, job_data=job_data, priority=5)

        assert result is False  # Should return False for duplicate

    @pytest.mark.asyncio
    async def test_enqueue_stores_metadata(self, priority_queue, mock_redis):
        """Test that enqueue stores priority and scheduling metadata."""
        pipeline_mock = AsyncMock()
        pipeline_mock.zadd = AsyncMock()
        pipeline_mock.set = AsyncMock()
        pipeline_mock.expire = AsyncMock()
        pipeline_mock.execute = AsyncMock(return_value=[1, True, True])
        pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
        pipeline_mock.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = pipeline_mock

        job_id = "meta-job"
        job_data = {"url": "https://example.com"}
        priority = 8
        scheduled_at = datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

        await priority_queue.enqueue(
            job_id=job_id, job_data=job_data, priority=priority, scheduled_at=scheduled_at
        )

        # Verify job data includes metadata
        pipeline_mock.set.assert_called_once()
        call_args = pipeline_mock.set.call_args
        stored_data = json.loads(call_args[0][1])

        assert stored_data["priority"] == priority
        assert stored_data["scheduled_at"] == scheduled_at.isoformat()
        assert stored_data["enqueued_at"] is not None
        assert stored_data["url"] == "https://example.com"


class TestDequeue:
    """Test job dequeuing functionality."""

    @pytest.mark.asyncio
    async def test_dequeue_success(self, priority_queue, mock_redis):
        """Test successfully dequeuing a job."""
        job_id = "test-job"
        job_data = {"priority": 10, "url": "https://example.com"}
        score = 123.45

        # Mock ZPOPMIN returns lowest score job
        mock_redis.zpopmin.return_value = [(job_id.encode(), score)]
        # Mock GET returns job data
        mock_redis.get.return_value = json.dumps(job_data).encode()
        # Mock DELETE
        mock_redis.delete = AsyncMock()

        result = await priority_queue.dequeue()

        assert result is not None
        dequeued_id, dequeued_data = result
        assert dequeued_id == job_id
        assert dequeued_data == job_data

    @pytest.mark.asyncio
    async def test_dequeue_empty_queue(self, priority_queue, mock_redis):
        """Test dequeuing from empty queue."""
        mock_redis.zpopmin.return_value = []

        result = await priority_queue.dequeue()

        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_missing_data(self, priority_queue, mock_redis):
        """Test dequeuing when job data is missing from Redis."""
        job_id = "orphan-job"
        score = 123.45

        # Job exists in sorted set
        mock_redis.zpopmin.return_value = [(job_id.encode(), score)]
        # But data is missing
        mock_redis.get.return_value = None

        result = await priority_queue.dequeue()

        # Should return None and log error
        assert result is None

    @pytest.mark.asyncio
    async def test_dequeue_cleans_up_data(self, priority_queue, mock_redis):
        """Test that dequeue removes job data after fetching."""
        job_id = "cleanup-job"
        job_data = {"test": "data"}

        mock_redis.zpopmin.return_value = [(job_id.encode(), 123.0)]
        mock_redis.get.return_value = json.dumps(job_data).encode()
        mock_redis.delete = AsyncMock()

        await priority_queue.dequeue()

        # Verify data was deleted
        mock_redis.delete.assert_called_once()


class TestRemove:
    """Test job removal functionality."""

    @pytest.mark.asyncio
    async def test_remove_success(self, priority_queue, mock_redis):
        """Test successfully removing a job."""
        job_id = "remove-job"

        # Setup mock pipeline
        pipeline_mock = AsyncMock()
        pipeline_mock.zrem = AsyncMock()
        pipeline_mock.delete = AsyncMock()
        pipeline_mock.execute = AsyncMock(return_value=[1, True])  # ZREM removed 1, DELETE ok
        pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
        pipeline_mock.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = pipeline_mock

        result = await priority_queue.remove(job_id)

        assert result is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_job(self, priority_queue, mock_redis):
        """Test removing a job that doesn't exist."""
        job_id = "nonexistent-job"

        # Setup mock pipeline
        pipeline_mock = AsyncMock()
        pipeline_mock.zrem = AsyncMock()
        pipeline_mock.delete = AsyncMock()
        pipeline_mock.execute = AsyncMock(return_value=[0, True])  # ZREM removed 0 (not found)
        pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
        pipeline_mock.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = pipeline_mock

        result = await priority_queue.remove(job_id)

        assert result is False


class TestPeek:
    """Test queue peeking functionality."""

    @pytest.mark.asyncio
    async def test_peek_single_job(self, priority_queue, mock_redis):
        """Test peeking at top job without removing it."""
        job_id = "peek-job"
        job_data = {"priority": 10}
        score = 123.0

        mock_redis.zrange.return_value = [(job_id.encode(), score)]
        mock_redis.get.return_value = json.dumps(job_data).encode()

        jobs = await priority_queue.peek(count=1)

        assert len(jobs) == 1
        assert jobs[0][0] == job_id
        assert jobs[0][1] == job_data

    @pytest.mark.asyncio
    async def test_peek_multiple_jobs(self, priority_queue, mock_redis):
        """Test peeking at multiple jobs."""
        jobs_data = [
            (b"job-1", 100.0, {"priority": 10}),
            (b"job-2", 200.0, {"priority": 5}),
            (b"job-3", 300.0, {"priority": 0}),
        ]

        mock_redis.zrange.return_value = [(jid, score) for jid, score, _ in jobs_data]

        # Mock GET to return job data in sequence
        async def mock_get(key):
            for jid, _, data in jobs_data:
                if key.endswith(jid.decode()):
                    return json.dumps(data).encode()
            return None

        mock_redis.get.side_effect = mock_get

        jobs = await priority_queue.peek(count=3)

        assert len(jobs) == 3
        assert jobs[0][0] == "job-1"
        assert jobs[1][0] == "job-2"
        assert jobs[2][0] == "job-3"

    @pytest.mark.asyncio
    async def test_peek_empty_queue(self, priority_queue, mock_redis):
        """Test peeking at empty queue."""
        mock_redis.zrange.return_value = []

        jobs = await priority_queue.peek(count=5)

        assert len(jobs) == 0


class TestGetQueueSize:
    """Test queue size functionality."""

    @pytest.mark.asyncio
    async def test_get_queue_size(self, priority_queue, mock_redis):
        """Test getting queue size."""
        mock_redis.zcard.return_value = 42

        size = await priority_queue.get_queue_size()

        assert size == 42
        mock_redis.zcard.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_queue_size_empty(self, priority_queue, mock_redis):
        """Test getting size of empty queue."""
        mock_redis.zcard.return_value = 0

        size = await priority_queue.get_queue_size()

        assert size == 0


class TestClear:
    """Test queue clearing functionality."""

    @pytest.mark.asyncio
    async def test_clear_queue(self, priority_queue, mock_redis):
        """Test clearing all jobs from queue."""
        job_ids = [b"job-1", b"job-2", b"job-3"]
        mock_redis.zrange.return_value = job_ids

        # Setup mock pipeline
        pipeline_mock = AsyncMock()
        pipeline_mock.delete = AsyncMock()
        pipeline_mock.execute = AsyncMock()
        pipeline_mock.__aenter__ = AsyncMock(return_value=pipeline_mock)
        pipeline_mock.__aexit__ = AsyncMock(return_value=None)
        mock_redis.pipeline.return_value = pipeline_mock

        count = await priority_queue.clear()

        assert count == 3
        # Verify all data keys and queue were deleted
        assert pipeline_mock.delete.call_count == 4  # 3 data keys + 1 queue key

    @pytest.mark.asyncio
    async def test_clear_empty_queue(self, priority_queue, mock_redis):
        """Test clearing empty queue."""
        mock_redis.zrange.return_value = []

        count = await priority_queue.clear()

        assert count == 0


class TestKeyManagement:
    """Test Redis key management."""

    def test_job_data_key_format(self, priority_queue):
        """Test job data key format."""
        job_id = "test-job-123"
        key = priority_queue._job_data_key(job_id)

        assert key == "test_queue:data:test-job-123"
        assert key.startswith(priority_queue.key_prefix)

    def test_queue_key_format(self, priority_queue):
        """Test queue key format."""
        assert priority_queue.queue_key == "test_queue:jobs"


class TestIntegrationScenarios:
    """Test realistic integration scenarios."""

    @pytest.mark.asyncio
    async def test_priority_ordering_integration(self, priority_queue, mock_redis):
        """Test that jobs are dequeued in correct priority order."""
        # Simulate enqueueing jobs with different priorities
        timestamp = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)

        # Calculate scores for different priorities (same timestamp)
        score_p10 = priority_queue._calculate_score(10, timestamp)
        score_p5 = priority_queue._calculate_score(5, timestamp)
        score_p0 = priority_queue._calculate_score(0, timestamp)

        # Verify ordering: lower score = dequeued first
        assert score_p10 < score_p5 < score_p0

        # Job data
        jobs = [
            ("low-priority", {"priority": 0}, score_p0),
            ("high-priority", {"priority": 10}, score_p10),
            ("mid-priority", {"priority": 5}, score_p5),
        ]

        # Simulate dequeuing in priority order
        mock_redis.zpopmin.return_value = [(jobs[1][0].encode(), jobs[1][2])]
        mock_redis.get.return_value = json.dumps(jobs[1][1]).encode()
        mock_redis.delete = AsyncMock()

        result = await priority_queue.dequeue()
        # First dequeued should be high priority
        assert result[0] == "high-priority"

    @pytest.mark.asyncio
    async def test_fifo_within_same_priority(self, priority_queue):
        """Test FIFO ordering within same priority level."""
        base_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=UTC)
        later_time = base_time + timedelta(seconds=1)

        # Same priority, different times
        score_early = priority_queue._calculate_score(5, base_time)
        score_late = priority_queue._calculate_score(5, later_time)

        # Earlier job should have lower score (dequeued first)
        assert score_early < score_late
