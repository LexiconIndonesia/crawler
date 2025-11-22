"""Integration tests for NATS queue with immediate cancellation.

Tests the full flow:
1. Job creation → NATS publish
2. Job cancellation → NATS queue removal
3. Worker behavior with cancelled jobs
"""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncConnection

from config import get_settings
from crawler.api.generated import CancelJobRequest, CreateSeedJobInlineRequest, GlobalConfig
from crawler.api.v1.services import JobService
from crawler.db.repositories import CrawlJobRepository, WebsiteRepository
from crawler.services.nats_queue import NATSQueueService
from crawler.services.redis_cache import JobCancellationFlag


@pytest.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:
    """Create Redis client for testing."""
    settings = get_settings()
    client = redis.from_url(settings.redis_url)
    yield client
    await client.aclose()


@pytest.fixture
async def cancellation_flag(redis_client: redis.Redis) -> JobCancellationFlag:
    """Create job cancellation flag service."""
    settings = get_settings()
    return JobCancellationFlag(redis_client, settings)


@pytest.fixture
def nats_queue_service() -> NATSQueueService:
    """Create mock NATS queue service."""
    settings = get_settings()
    service = NATSQueueService(settings)
    # Mock the internal attributes to avoid actual NATS connection
    service.client = AsyncMock()
    service.js = AsyncMock()
    return service


@pytest.fixture
async def job_service(
    db_connection: AsyncConnection,
    cancellation_flag: JobCancellationFlag,
    nats_queue_service: NATSQueueService,
) -> JobService:
    """Create job service with all dependencies."""
    crawl_job_repo = CrawlJobRepository(db_connection)
    website_repo = WebsiteRepository(db_connection)

    return JobService(
        crawl_job_repo=crawl_job_repo,
        website_repo=website_repo,
        cancellation_flag=cancellation_flag,
        nats_queue=nats_queue_service,
    )


class TestNATSQueueCancellation:
    """Integration tests for NATS queue with cancellation."""

    async def test_job_published_to_queue_on_creation(
        self,
        job_service: JobService,
        nats_queue_service: NATSQueueService,
    ) -> None:
        """Test that job is published to NATS queue when created."""
        # Mock publish_job to return success
        nats_queue_service.publish_job = AsyncMock(return_value=True)

        # Create inline job request
        from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum

        request = CreateSeedJobInlineRequest(
            seed_url="https://example.com/test",
            steps=[
                CrawlStep(
                    name="test_step",
                    type=StepTypeEnum.crawl,
                    method=MethodEnum.http,
                    config=StepConfig(url="https://example.com/test"),
                )
            ],
            global_config=GlobalConfig(),
            priority=5,
        )

        # Create job
        response = await job_service.create_seed_job_inline(request)

        # Verify job was published to queue
        nats_queue_service.publish_job.assert_called_once()
        call_args = nats_queue_service.publish_job.call_args
        assert call_args[0][0] == str(response.id)  # job_id (converted to string)
        assert call_args[0][1]["seed_url"] == str(request.seed_url)
        assert call_args[0][1]["priority"] == request.priority

    async def test_job_removed_from_queue_on_cancellation(
        self,
        job_service: JobService,
        nats_queue_service: NATSQueueService,
        cancellation_flag: JobCancellationFlag,
    ) -> None:
        """Test that pending job is removed from queue when cancelled."""
        # Mock NATS operations
        nats_queue_service.publish_job = AsyncMock(return_value=True)
        nats_queue_service.delete_job_from_queue = AsyncMock(return_value=True)

        # Create job
        from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum

        request = CreateSeedJobInlineRequest(
            seed_url="https://example.com/cancel-test",
            steps=[
                CrawlStep(
                    name="test_step",
                    type=StepTypeEnum.crawl,
                    method=MethodEnum.http,
                    config=StepConfig(url="https://example.com/cancel-test"),
                )
            ],
            global_config=GlobalConfig(),
            priority=5,
        )

        job_response = await job_service.create_seed_job_inline(request)

        # Cancel the job
        cancel_request = CancelJobRequest(reason="Test cancellation")
        cancel_response = await job_service.cancel_job(job_response.id, cancel_request)

        # Verify job was removed from queue
        nats_queue_service.delete_job_from_queue.assert_called_once_with(job_response.id)

        # Verify cancellation flag was set
        is_cancelled = await cancellation_flag.is_cancelled(job_response.id)
        assert is_cancelled is True

        # Verify job status is cancelled
        from crawler.api.generated import StatusEnum

        assert cancel_response.status.status == StatusEnum.cancelled

        # Cleanup
        await cancellation_flag.clear_cancellation(job_response.id)

    async def test_running_job_not_removed_from_queue(
        self,
        job_service: JobService,
        nats_queue_service: NATSQueueService,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that running job is not removed from queue (only Redis flag set)."""
        # Mock NATS operations
        nats_queue_service.publish_job = AsyncMock(return_value=True)
        nats_queue_service.delete_job_from_queue = AsyncMock(return_value=False)

        # Create job
        from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum

        request = CreateSeedJobInlineRequest(
            seed_url="https://example.com/running-test",
            steps=[
                CrawlStep(
                    name="test_step",
                    type=StepTypeEnum.crawl,
                    method=MethodEnum.http,
                    config=StepConfig(url="https://example.com/running-test"),
                )
            ],
            global_config=GlobalConfig(),
            priority=5,
        )

        job_response = await job_service.create_seed_job_inline(request)

        # Update job to running status
        job_repo = CrawlJobRepository(db_connection)
        await job_repo.update_status(
            job_id=job_response.id,
            status="running",
            started_at=None,
            completed_at=None,
            error_message=None,
        )

        # Try to cancel the job
        cancel_request = CancelJobRequest(reason="Test cancellation of running job")
        cancel_response = await job_service.cancel_job(job_response.id, cancel_request)

        # Verify delete_job_from_queue was NOT called (job is running, not pending)
        nats_queue_service.delete_job_from_queue.assert_not_called()

        # Verify job status is cancelled
        from crawler.api.generated import StatusEnum

        assert cancel_response.status.status == StatusEnum.cancelled

    @patch("crawler.services.nats_queue.nats.connect")
    async def test_publish_failure_does_not_prevent_job_creation(
        self,
        mock_connect: AsyncMock,
        job_service: JobService,
        nats_queue_service: NATSQueueService,
    ) -> None:
        """Test that NATS publish failure doesn't prevent job creation."""
        # Mock NATS to fail on publish
        nats_queue_service.publish_job = AsyncMock(return_value=False)

        # Create job
        from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum

        request = CreateSeedJobInlineRequest(
            seed_url="https://example.com/publish-fail-test",
            steps=[
                CrawlStep(
                    name="test_step",
                    type=StepTypeEnum.crawl,
                    method=MethodEnum.http,
                    config=StepConfig(url="https://example.com/publish-fail-test"),
                )
            ],
            global_config=GlobalConfig(),
            priority=5,
        )

        # Should not raise exception
        job_response = await job_service.create_seed_job_inline(request)

        # Verify job was created despite publish failure
        assert job_response.id is not None
        from crawler.api.generated import StatusEnum

        assert job_response.status.status == StatusEnum.pending

        # Verify publish was attempted
        nats_queue_service.publish_job.assert_called_once()


class TestNATSQueueMessageFormat:
    """Tests for NATS message format and structure."""

    async def test_message_contains_required_fields(
        self,
        job_service: JobService,
        nats_queue_service: NATSQueueService,
    ) -> None:
        """Test that published messages contain all required fields."""
        # Capture the published message
        published_messages = []

        async def capture_publish(job_id: str, job_data: dict) -> bool:
            published_messages.append({"job_id": job_id, "job_data": job_data})
            return True

        nats_queue_service.publish_job = capture_publish

        # Create job
        from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum

        request = CreateSeedJobInlineRequest(
            seed_url="https://example.com/message-format-test",
            steps=[
                CrawlStep(
                    name="test_step",
                    type=StepTypeEnum.crawl,
                    method=MethodEnum.http,
                    config=StepConfig(url="https://example.com/message-format-test"),
                )
            ],
            global_config=GlobalConfig(),
            priority=7,
        )

        job_response = await job_service.create_seed_job_inline(request)

        # Verify message was captured
        assert len(published_messages) == 1
        message = published_messages[0]

        # Verify required fields
        assert message["job_id"] == str(job_response.id)  # job_id (converted to string)
        assert "seed_url" in message["job_data"]
        assert "job_type" in message["job_data"]
        assert "priority" in message["job_data"]
        assert message["job_data"]["priority"] == 7
        assert message["job_data"]["has_inline_config"] is True
