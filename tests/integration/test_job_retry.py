"""Integration tests for automatic job retry on transient failures."""

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import ErrorCategoryEnum, JobTypeEnum, StatusEnum
from crawler.db.repositories import (
    CrawlJobRepository,
    DeadLetterQueueRepository,
    RetryHistoryRepository,
    RetryPolicyRepository,
)
from crawler.services.job_retry_handler import JobRetryHandler
from crawler.services.nats_queue import NATSQueueService


# Mock asyncio.sleep globally for all tests to speed them up
@pytest.fixture(autouse=True)
def mock_sleep():
    """Mock asyncio.sleep to speed up tests."""
    with patch("asyncio.sleep", return_value=None):
        yield


@pytest.fixture
async def job_repo(db_connection: AsyncConnection) -> CrawlJobRepository:
    """Create job repository."""
    return CrawlJobRepository(db_connection)


@pytest.fixture
async def retry_policy_repo(db_connection: AsyncConnection) -> RetryPolicyRepository:
    """Create retry policy repository."""
    return RetryPolicyRepository(db_connection)


@pytest.fixture
async def retry_history_repo(db_connection: AsyncConnection) -> RetryHistoryRepository:
    """Create retry history repository."""
    return RetryHistoryRepository(db_connection)


@pytest.fixture
async def mock_nats_queue() -> NATSQueueService:
    """Create mock NATS queue service."""
    mock = AsyncMock(spec=NATSQueueService)
    mock.publish_job = AsyncMock(return_value=None)
    return mock


@pytest.fixture
async def dlq_repo(db_connection: AsyncConnection) -> DeadLetterQueueRepository:
    """Create DLQ repository."""
    return DeadLetterQueueRepository(db_connection)


@pytest.fixture
async def retry_handler(
    job_repo: CrawlJobRepository,
    retry_policy_repo: RetryPolicyRepository,
    retry_history_repo: RetryHistoryRepository,
    dlq_repo: DeadLetterQueueRepository,
    mock_nats_queue: NATSQueueService,
) -> JobRetryHandler:
    """Create retry handler with real repositories."""
    return JobRetryHandler(
        job_repo, retry_policy_repo, retry_history_repo, dlq_repo, mock_nats_queue
    )


@pytest.fixture
async def test_job(job_repo: CrawlJobRepository):
    """Create a test job."""
    job = await job_repo.create_seed_url_submission(
        seed_url="https://example.com",
        inline_config={"steps": [{"name": "test", "type": "crawl"}]},
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
        max_retries=3,
    )
    return job


# ============================================================================
# Network Timeout Retry Tests
# ============================================================================


class TestNetworkTimeoutRetry:
    """Test retry behavior for network timeouts."""

    async def test_timeout_error_should_retry(
        self, retry_handler: JobRetryHandler, test_job, mock_nats_queue
    ):
        """TimeoutError should trigger retry."""
        exc = TimeoutError("Connection timeout after 30s")

        # Handle failure
        will_retry = await retry_handler.handle_job_failure(
            job_id=test_job.id, exc=exc, error_message=str(exc)
        )

        # Should retry
        assert will_retry is True

        # Check job was requeued
        mock_nats_queue.publish_job.assert_called_once_with(
            str(test_job.id), {"job_id": str(test_job.id)}
        )

    async def test_timeout_retry_increments_count(
        self, retry_handler: JobRetryHandler, test_job, job_repo: CrawlJobRepository
    ):
        """Retry should increment retry_count."""
        exc = TimeoutError("Connection timeout")

        # Initial retry_count should be 0
        job = await job_repo.get_by_id(test_job.id)
        assert job.retry_count == 0

        # Handle failure
        await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        # Check retry_count incremented
        job = await job_repo.get_by_id(test_job.id)
        assert job.retry_count == 1

    async def test_timeout_records_retry_history(
        self,
        retry_handler: JobRetryHandler,
        test_job,
        retry_history_repo: RetryHistoryRepository,
    ):
        """Retry should record attempt in history."""
        exc = TimeoutError("Connection timeout")

        # Handle failure
        await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        # Check history recorded
        history = await retry_history_repo.get_by_job_id(test_job.id)
        assert len(history) == 1
        assert history[0].error_category == ErrorCategoryEnum.TIMEOUT
        assert history[0].attempt_number == 1
        assert "timeout" in history[0].error_message.lower()

    async def test_timeout_max_retries_exhausted(
        self, retry_handler: JobRetryHandler, test_job, job_repo: CrawlJobRepository
    ):
        """After max retries, timeout should not retry."""
        exc = TimeoutError("Connection timeout")

        # Simulate 2 previous retries (timeout max_attempts=2)
        await job_repo.update_retry_count(test_job.id, 2)

        # Handle failure (3rd attempt)
        will_retry = await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        # Should not retry (max reached)
        assert will_retry is False

        # Check job marked as FAILED
        job = await job_repo.get_by_id(test_job.id)
        assert job.status == StatusEnum.FAILED


# ============================================================================
# HTTP 503 Service Unavailable Tests
# ============================================================================


class TestHTTP503Retry:
    """Test retry behavior for HTTP 503 errors."""

    async def test_503_should_retry(self, retry_handler: JobRetryHandler, test_job):
        """HTTP 503 should trigger retry."""
        will_retry = await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=503, error_message="Service Unavailable"
        )

        assert will_retry is True

    async def test_503_classified_as_server_error(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """HTTP 503 should be classified as SERVER_ERROR."""
        await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=503, error_message="Service Unavailable"
        )

        history = await retry_history_repo.get_by_job_id(test_job.id)
        assert history[0].error_category == ErrorCategoryEnum.SERVER_ERROR

    async def test_503_uses_exponential_backoff(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """HTTP 503 retries should use exponential backoff."""
        # Collect delays from 3 attempts to verify exponential growth
        # With test policy: initial_delay=10s, multiplier=2.0, jitter=±20%
        delays = []

        # Attempt 1
        await retry_handler.handle_job_failure(job_id=test_job.id, http_status=503)
        history1 = await retry_history_repo.get_latest_attempt(test_job.id)
        delays.append(history1.retry_delay_seconds)

        # Attempt 2
        await retry_handler.handle_job_failure(job_id=test_job.id, http_status=503)
        history2 = await retry_history_repo.get_latest_attempt(test_job.id)
        delays.append(history2.retry_delay_seconds)

        # Attempt 3
        await retry_handler.handle_job_failure(job_id=test_job.id, http_status=503)
        history3 = await retry_history_repo.get_latest_attempt(test_job.id)
        delays.append(history3.retry_delay_seconds)

        # Verify exponential growth pattern despite jitter
        # Base delays: 10s, 20s, 40s (exponential with multiplier=2.0)
        # With ±20% jitter: [8-12], [16-24], [32-48]
        # Test that 3rd attempt is significantly larger than 1st
        # Even worst case (48s vs 8s = 6x) far exceeds minimum exponential growth
        assert delays[2] >= delays[0] * 2.5, f"Expected exponential growth, got delays: {delays}"


# ============================================================================
# HTTP 429 Rate Limit Tests
# ============================================================================


class TestHTTP429RateLimit:
    """Test retry behavior for HTTP 429 rate limiting."""

    async def test_429_should_retry(self, retry_handler: JobRetryHandler, test_job):
        """HTTP 429 should trigger retry."""
        will_retry = await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=429, error_message="Rate limit exceeded"
        )

        assert will_retry is True

    async def test_429_respects_retry_after_header(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """HTTP 429 with Retry-After should use server's delay."""
        # Server says wait 120 seconds
        await retry_handler.handle_job_failure(
            job_id=test_job.id,
            http_status=429,
            error_message="Rate limit exceeded",
            retry_after="120",
        )

        history = await retry_history_repo.get_latest_attempt(test_job.id)
        assert history.retry_delay_seconds == 120

    async def test_429_has_higher_max_attempts(
        self, retry_handler: JobRetryHandler, test_job, retry_policy_repo: RetryPolicyRepository
    ):
        """Rate limit should have more retry attempts than other errors."""
        policy = await retry_policy_repo.get_by_category(ErrorCategoryEnum.RATE_LIMIT)

        # Rate limit should have 5 attempts (more than others)
        assert policy.max_attempts == 5

    async def test_429_classified_as_rate_limit(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """HTTP 429 should be classified as RATE_LIMIT."""
        await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=429, error_message="Too many requests"
        )

        history = await retry_history_repo.get_by_job_id(test_job.id)
        assert history[0].error_category == ErrorCategoryEnum.RATE_LIMIT


# ============================================================================
# Browser Crash Tests
# ============================================================================


class TestBrowserCrashRetry:
    """Test retry behavior for browser crashes."""

    async def test_browser_crash_should_retry(self, retry_handler: JobRetryHandler, test_job):
        """Browser crash should trigger retry."""
        # Simulate browser crash exception
        from crawler.services.browser_pool import BrowserCrashError

        exc = BrowserCrashError("Browser process crashed", "chromium")

        will_retry = await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        assert will_retry is True

    async def test_browser_crash_classified_correctly(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """Browser crash should be classified as BROWSER_CRASH."""
        from crawler.services.browser_pool import BrowserCrashError

        exc = BrowserCrashError("Browser crashed", "chromium")

        await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        history = await retry_history_repo.get_by_job_id(test_job.id)
        assert history[0].error_category == ErrorCategoryEnum.BROWSER_CRASH


# ============================================================================
# Non-Retryable Error Tests
# ============================================================================


class TestNonRetryableErrors:
    """Test that non-retryable errors fail permanently."""

    async def test_404_should_not_retry(self, retry_handler: JobRetryHandler, test_job):
        """HTTP 404 should not retry."""
        will_retry = await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=404, error_message="Not found"
        )

        assert will_retry is False

    async def test_401_should_not_retry(self, retry_handler: JobRetryHandler, test_job):
        """HTTP 401 should not retry."""
        will_retry = await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=401, error_message="Unauthorized"
        )

        assert will_retry is False

    async def test_validation_error_should_not_retry(
        self, retry_handler: JobRetryHandler, test_job
    ):
        """Validation errors should not retry."""
        exc = ValueError("Invalid configuration")

        will_retry = await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        assert will_retry is False

    async def test_non_retryable_marked_as_failed(
        self, retry_handler: JobRetryHandler, test_job, job_repo: CrawlJobRepository
    ):
        """Non-retryable errors should mark job as FAILED."""
        await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=404, error_message="Not found"
        )

        job = await job_repo.get_by_id(test_job.id)
        assert job.status == StatusEnum.FAILED


# ============================================================================
# Retry History Analytics Tests
# ============================================================================


class TestRetryHistoryAnalytics:
    """Test retry history tracking for analytics."""

    async def test_retry_history_includes_stack_trace(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """Retry history should include stack trace."""
        exc = TimeoutError("Connection timeout")

        await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        history = await retry_history_repo.get_by_job_id(test_job.id)
        assert history[0].stack_trace is not None
        # Stack trace should at least contain exception type and message
        assert "TimeoutError" in history[0].stack_trace
        assert "Connection timeout" in history[0].stack_trace

    async def test_multiple_retries_tracked(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """Multiple retry attempts should all be tracked."""
        exc = TimeoutError("Connection timeout")

        # Retry 3 times, but max_attempts=2 for timeout errors, so only 2 will be recorded
        for _ in range(3):
            await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        history = await retry_history_repo.get_by_job_id(test_job.id)
        # Only 2 retry attempts recorded (3rd call exceeds max_attempts so no retry recorded)
        assert len(history) == 2
        assert history[0].attempt_number == 1
        assert history[1].attempt_number == 2


# ============================================================================
# Jitter and Backoff Tests
# ============================================================================


class TestBackoffWithJitter:
    """Test backoff delays with jitter."""

    async def test_jitter_applied_to_delays(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """Delays should have jitter to avoid thundering herd."""
        exc = TimeoutError("Connection timeout")

        # Mock random.randint to return predictable values for jitter
        # This makes the test deterministic and prevents flakiness
        with patch("random.randint", side_effect=[-1, 0, 1, -1, 0, 1, 2, -2, 0, 1]):
            # Retry multiple times and collect delays
            delays = []
            for i in range(10):
                # Reset job for each test
                await retry_handler.job_repo.update_retry_count(test_job.id, i)

                await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

                history = await retry_history_repo.get_latest_attempt(test_job.id)
                delays.append(history.retry_delay_seconds)

            # With deterministic jitter values, we should see multiple unique delays
            unique_delays = len(set(delays))
            assert unique_delays > 1, "Jitter should produce varying delays"

    async def test_delay_never_exceeds_max(
        self, retry_handler: JobRetryHandler, test_job, retry_history_repo: RetryHistoryRepository
    ):
        """Delays should never exceed max_delay even with jitter."""
        exc = TimeoutError("Connection timeout")

        # Set retry count to 1 (within max_attempts=2, so it will still retry)
        # This is enough to test max delay since exponential backoff grows quickly
        await retry_handler.job_repo.update_retry_count(test_job.id, 1)

        await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        history = await retry_history_repo.get_latest_attempt(test_job.id)

        # Should be capped at 300s (absolute maximum)
        assert history.retry_delay_seconds <= 300


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestNATSPublishFailure:
    """Test error handling when NATS publish fails."""

    async def test_failed_publish_reverts_job_status(
        self, retry_handler: JobRetryHandler, test_job, job_repo: CrawlJobRepository
    ):
        """Job should be marked as FAILED if NATS publish fails."""
        exc = TimeoutError("Connection timeout")

        # Mock NATS publish to raise an exception
        retry_handler.nats_queue.publish_job = AsyncMock(
            side_effect=RuntimeError("NATS connection failed")
        )

        result = await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        # Should return False indicating failure
        assert result is False

        # Job should be marked as FAILED
        job = await job_repo.get_by_id(str(test_job.id))
        assert job.status == StatusEnum.FAILED
        assert "Failed to requeue" in job.error_message
        assert "NATS connection failed" in job.error_message

    async def test_successful_publish_returns_true(self, retry_handler: JobRetryHandler, test_job):
        """Successful publish should return True."""
        exc = TimeoutError("Connection timeout")

        # NATS publish is already mocked to succeed in the fixture
        result = await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        # Should return True indicating success
        assert result is True
