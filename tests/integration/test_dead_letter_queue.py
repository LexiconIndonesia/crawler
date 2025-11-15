"""Integration tests for Dead Letter Queue (DLQ) system."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import ErrorCategoryEnum, JobTypeEnum
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
# DLQ Entry Creation Tests
# ============================================================================


class TestDLQEntryCreation:
    """Test that jobs are added to DLQ when permanently failed."""

    async def test_non_retryable_error_added_to_dlq(
        self, retry_handler: JobRetryHandler, test_job, dlq_repo: DeadLetterQueueRepository
    ):
        """Non-retryable errors should add job to DLQ."""
        # Handle a 404 error (non-retryable)
        will_retry = await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=404, error_message="Page not found"
        )

        # Should not retry
        assert will_retry is False

        # Should be in DLQ
        dlq_entry = await dlq_repo.get_by_job_id(str(test_job.id))
        assert dlq_entry is not None
        assert dlq_entry.job_id == test_job.id
        assert dlq_entry.error_category == ErrorCategoryEnum.NOT_FOUND
        assert dlq_entry.error_message == "Page not found"
        assert dlq_entry.http_status == 404

    async def test_max_retries_exhausted_added_to_dlq(
        self,
        retry_handler: JobRetryHandler,
        test_job,
        job_repo: CrawlJobRepository,
        dlq_repo: DeadLetterQueueRepository,
    ):
        """Jobs that exhaust max retries should be added to DLQ."""
        # Simulate max retries exhausted for timeout
        await job_repo.update_retry_count(test_job.id, 2)  # Timeout max_attempts=2

        # Handle failure after max retries
        exc = TimeoutError("Connection timeout")
        will_retry = await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc)

        # Should not retry (max reached)
        assert will_retry is False

        # Should be in DLQ
        dlq_entry = await dlq_repo.get_by_job_id(str(test_job.id))
        assert dlq_entry is not None
        assert dlq_entry.error_category == ErrorCategoryEnum.TIMEOUT
        assert dlq_entry.total_attempts == 3  # Initial + 2 retries
        assert "timeout" in dlq_entry.error_message.lower()

    async def test_dlq_entry_includes_job_metadata(
        self, retry_handler: JobRetryHandler, test_job, dlq_repo: DeadLetterQueueRepository
    ):
        """DLQ entry should include all relevant job metadata."""
        await retry_handler.handle_job_failure(
            job_id=test_job.id, http_status=404, error_message="Not found"
        )

        dlq_entry = await dlq_repo.get_by_job_id(str(test_job.id))
        assert dlq_entry.seed_url == str(test_job.seed_url)
        assert dlq_entry.job_type == test_job.job_type
        assert dlq_entry.priority == test_job.priority
        assert dlq_entry.retry_attempted is False
        assert dlq_entry.resolved_at is None


# ============================================================================
# DLQ Query Tests
# ============================================================================


class TestDLQQueries:
    """Test DLQ query operations."""

    async def test_list_dlq_entries(self, dlq_repo: DeadLetterQueueRepository, test_job):
        """Test listing DLQ entries."""
        # Add entry manually
        await dlq_repo.add_to_dlq(
            job_id=str(test_job.id),
            seed_url="https://example.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NOT_FOUND,
            error_message="Page not found",
            stack_trace=None,
            http_status=404,
            total_attempts=1,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # List entries
        entries = await dlq_repo.list_entries()
        assert len(entries) >= 1
        assert any(e.job_id == test_job.id for e in entries)

    async def test_filter_dlq_by_error_category(
        self, dlq_repo: DeadLetterQueueRepository, job_repo: CrawlJobRepository
    ):
        """Test filtering DLQ entries by error category."""
        # Create two test jobs
        job1 = await job_repo.create_seed_url_submission(
            seed_url="https://example1.com",
            inline_config={"steps": [{"name": "test", "type": "crawl"}]},
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            max_retries=3,
        )

        job2 = await job_repo.create_seed_url_submission(
            seed_url="https://example2.com",
            inline_config={"steps": [{"name": "test", "type": "crawl"}]},
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            max_retries=3,
        )

        # Add DLQ entries with different categories
        await dlq_repo.add_to_dlq(
            job_id=str(job1.id),
            seed_url="https://example1.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NOT_FOUND,
            error_message="Not found",
            stack_trace=None,
            http_status=404,
            total_attempts=1,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        await dlq_repo.add_to_dlq(
            job_id=str(job2.id),
            seed_url="https://example2.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.TIMEOUT,
            error_message="Timeout",
            stack_trace=None,
            http_status=None,
            total_attempts=3,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Filter by NOT_FOUND
        not_found_entries = await dlq_repo.list_entries(error_category=ErrorCategoryEnum.NOT_FOUND)
        assert all(e.error_category == ErrorCategoryEnum.NOT_FOUND for e in not_found_entries)

        # Filter by TIMEOUT
        timeout_entries = await dlq_repo.list_entries(error_category=ErrorCategoryEnum.TIMEOUT)
        assert all(e.error_category == ErrorCategoryEnum.TIMEOUT for e in timeout_entries)

    async def test_filter_unresolved_only(
        self, dlq_repo: DeadLetterQueueRepository, job_repo: CrawlJobRepository
    ):
        """Test filtering for unresolved DLQ entries."""
        job = await job_repo.create_seed_url_submission(
            seed_url="https://example.com",
            inline_config={"steps": [{"name": "test", "type": "crawl"}]},
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            max_retries=3,
        )

        # Add unresolved entry
        entry = await dlq_repo.add_to_dlq(
            job_id=str(job.id),
            seed_url="https://example.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NOT_FOUND,
            error_message="Not found",
            stack_trace=None,
            http_status=404,
            total_attempts=1,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Filter for unresolved
        unresolved = await dlq_repo.list_entries(unresolved_only=True)
        assert len(unresolved) >= 1
        assert all(e.resolved_at is None for e in unresolved)

        # Resolve the entry
        await dlq_repo.mark_resolved(entry.id, "Fixed manually")

        # Filter for unresolved again
        unresolved_after = await dlq_repo.list_entries(unresolved_only=True)
        # Should not include the resolved entry
        assert not any(e.id == entry.id for e in unresolved_after)

    async def test_count_dlq_entries(self, dlq_repo: DeadLetterQueueRepository, test_job):
        """Test counting DLQ entries."""
        initial_count = await dlq_repo.count_entries()

        # Add entry
        await dlq_repo.add_to_dlq(
            job_id=str(test_job.id),
            seed_url="https://example.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NOT_FOUND,
            error_message="Not found",
            stack_trace=None,
            http_status=404,
            total_attempts=1,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Count should increase
        new_count = await dlq_repo.count_entries()
        assert new_count == initial_count + 1


# ============================================================================
# DLQ Management Tests
# ============================================================================


class TestDLQManagement:
    """Test DLQ management operations."""

    async def test_mark_retry_attempted_success(
        self, dlq_repo: DeadLetterQueueRepository, test_job
    ):
        """Test marking a DLQ entry as retried successfully."""
        entry = await dlq_repo.add_to_dlq(
            job_id=str(test_job.id),
            seed_url="https://example.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.TIMEOUT,
            error_message="Timeout",
            stack_trace=None,
            http_status=None,
            total_attempts=3,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Mark as retry attempted (success)
        updated = await dlq_repo.mark_retry_attempted(entry.id, success=True)

        assert updated.retry_attempted is True
        assert updated.retry_success is True
        assert updated.retry_attempted_at is not None

    async def test_mark_retry_attempted_failure(
        self, dlq_repo: DeadLetterQueueRepository, test_job
    ):
        """Test marking a DLQ entry as retried but failed again."""
        entry = await dlq_repo.add_to_dlq(
            job_id=str(test_job.id),
            seed_url="https://example.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NETWORK,
            error_message="Network error",
            stack_trace=None,
            http_status=None,
            total_attempts=3,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Mark as retry attempted (failure)
        updated = await dlq_repo.mark_retry_attempted(entry.id, success=False)

        assert updated.retry_attempted is True
        assert updated.retry_success is False
        assert updated.retry_attempted_at is not None

    async def test_mark_resolved(self, dlq_repo: DeadLetterQueueRepository, test_job):
        """Test marking a DLQ entry as resolved."""
        entry = await dlq_repo.add_to_dlq(
            job_id=str(test_job.id),
            seed_url="https://example.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NOT_FOUND,
            error_message="Not found",
            stack_trace=None,
            http_status=404,
            total_attempts=1,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Mark as resolved
        resolution_notes = "URL was temporarily unavailable, now fixed"
        updated = await dlq_repo.mark_resolved(entry.id, resolution_notes)

        assert updated.resolved_at is not None
        assert updated.resolution_notes == resolution_notes

    async def test_get_dlq_stats(
        self, dlq_repo: DeadLetterQueueRepository, job_repo: CrawlJobRepository
    ):
        """Test getting DLQ statistics."""
        # Create multiple entries with different states
        jobs = []
        for i in range(3):
            job = await job_repo.create_seed_url_submission(
                seed_url=f"https://example{i}.com",
                inline_config={"steps": [{"name": "test", "type": "crawl"}]},
                job_type=JobTypeEnum.ONE_TIME,
                priority=5,
                max_retries=3,
            )
            jobs.append(job)

        # Add 3 entries
        entry1 = await dlq_repo.add_to_dlq(
            job_id=str(jobs[0].id),
            seed_url="https://example0.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NOT_FOUND,
            error_message="Not found",
            stack_trace=None,
            http_status=404,
            total_attempts=1,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        entry2 = await dlq_repo.add_to_dlq(
            job_id=str(jobs[1].id),
            seed_url="https://example1.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.TIMEOUT,
            error_message="Timeout",
            stack_trace=None,
            http_status=None,
            total_attempts=3,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        await dlq_repo.add_to_dlq(
            job_id=str(jobs[2].id),
            seed_url="https://example2.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NETWORK,
            error_message="Network error",
            stack_trace=None,
            http_status=None,
            total_attempts=3,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Resolve one entry
        await dlq_repo.mark_resolved(entry1.id, "Fixed")

        # Mark one retry attempted successfully
        await dlq_repo.mark_retry_attempted(entry2.id, success=True)

        # Get stats
        stats = await dlq_repo.get_stats()

        assert stats.total_entries >= 3
        assert stats.unresolved_count >= 2  # entry2 and entry3
        assert stats.retry_attempted_count >= 1  # entry2
        assert stats.retry_success_count >= 1  # entry2

    async def test_get_oldest_unresolved(
        self, dlq_repo: DeadLetterQueueRepository, job_repo: CrawlJobRepository
    ):
        """Test getting oldest unresolved DLQ entries."""
        # Add entries at different times
        job1 = await job_repo.create_seed_url_submission(
            seed_url="https://old.com",
            inline_config={"steps": [{"name": "test", "type": "crawl"}]},
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            max_retries=3,
        )

        await dlq_repo.add_to_dlq(
            job_id=str(job1.id),
            seed_url="https://old.com",
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.TIMEOUT,
            error_message="Old timeout",
            stack_trace=None,
            http_status=None,
            total_attempts=3,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

        # Get oldest unresolved
        oldest = await dlq_repo.get_oldest_unresolved(limit=1)

        assert len(oldest) >= 1
        # Should include our old entry among the oldest
        assert any(e.job_id == job1.id for e in oldest)


# ============================================================================
# DLQ Stack Trace Tests
# ============================================================================


class TestDLQStackTraces:
    """Test that stack traces are properly recorded in DLQ."""

    async def test_dlq_includes_stack_trace(
        self, retry_handler: JobRetryHandler, test_job, dlq_repo: DeadLetterQueueRepository
    ):
        """DLQ entry should include stack trace when exception provided."""
        exc = ValueError("Invalid configuration")

        await retry_handler.handle_job_failure(job_id=test_job.id, exc=exc, error_message=str(exc))

        dlq_entry = await dlq_repo.get_by_job_id(str(test_job.id))
        assert dlq_entry.stack_trace is not None
        # Stack trace should at least contain exception type and message
        assert "ValueError" in dlq_entry.stack_trace
        assert "Invalid configuration" in dlq_entry.stack_trace
