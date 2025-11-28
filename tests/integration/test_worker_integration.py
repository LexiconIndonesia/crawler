"""Integration tests for worker with real crawl execution."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncConnection

from config import get_settings
from crawler.db.repositories import CrawlJobRepository
from crawler.services.nats_queue import NATSQueueService
from crawler.services.redis_cache import JobCancellationFlag, URLDeduplicationCache
from crawler.worker import CrawlJobWorker


@pytest.fixture
async def redis_client() -> AsyncGenerator[redis.Redis]:
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
async def dedup_cache(redis_client: redis.Redis) -> URLDeduplicationCache:
    """Create URL deduplication cache service."""
    settings = get_settings()
    return URLDeduplicationCache(redis_client, settings)


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
async def worker(
    nats_queue_service: NATSQueueService,
    cancellation_flag: JobCancellationFlag,
    dedup_cache: URLDeduplicationCache,
) -> CrawlJobWorker:
    """Create worker with mocked NATS."""
    settings = get_settings()
    return CrawlJobWorker(
        nats_queue=nats_queue_service,
        cancellation_flag=cancellation_flag,
        dedup_cache=dedup_cache,
        settings=settings,
    )


class TestWorkerIntegration:
    """Integration tests for worker with crawl execution."""

    async def test_worker_processes_inline_job(
        self,
        worker: CrawlJobWorker,
        db_connection: AsyncConnection,
    ) -> None:
        """Test worker processes inline job successfully."""
        # Create a job with inline config
        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create_seed_url_submission(
            seed_url="https://example.com/test",
            inline_config={
                "steps": [
                    {
                        "name": "test_step",
                        "type": "crawl",
                        "method": "http",
                        "config": {"url": "https://example.com/test"},
                        "selectors": {"detail_urls": "a"},
                    }
                ],
                "global_config": {},
            },
            variables=None,
            job_type="one_time",
            priority=5,
            scheduled_at=None,
            max_retries=3,
            metadata=None,
        )

        assert job is not None
        job_id = str(job.id)

        # Commit the job so it's visible
        await db_connection.commit()
        # Start new transaction for worker processing
        transaction = await db_connection.begin()

        # Mock HTTP response
        mock_html = '<html><body><a href="/product1">Product 1</a></body></html>'

        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = mock_html
            mock_response.headers = {"content-type": "text/html"}
            mock_request.return_value = mock_response

            # Process the job - pass connection so worker uses same transaction
            result = await worker.process_job(
                job_id, {"seed_url": job.seed_url}, conn=db_connection
            )

            # Verify job was processed successfully
            assert result is True

            # Commit worker changes
            await transaction.commit()

            # Start new transaction for verification
            transaction = await db_connection.begin()

            # Verify job status was updated
            updated_job = await job_repo.get_by_id(job_id)
            assert updated_job is not None
            assert updated_job.status.value == "completed"

            # Commit verification transaction so fixture can clean up properly
            await transaction.commit()

    async def test_worker_handles_cancelled_job(
        self,
        worker: CrawlJobWorker,
        db_connection: AsyncConnection,
        cancellation_flag: JobCancellationFlag,
    ) -> None:
        """Test worker handles cancelled job gracefully."""
        # Create a job
        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create_seed_url_submission(
            seed_url="https://example.com/cancelled",
            inline_config={
                "steps": [
                    {
                        "name": "test_step",
                        "type": "crawl",
                        "method": "http",
                        "config": {"url": "https://example.com/cancelled"},
                        "selectors": {"detail_urls": "a"},
                    }
                ],
                "global_config": {},
            },
            variables=None,
            job_type="one_time",
            priority=5,
            scheduled_at=None,
            max_retries=3,
            metadata=None,
        )

        assert job is not None
        job_id = str(job.id)

        # Commit the job
        await db_connection.commit()
        # Start new transaction for worker processing
        transaction = await db_connection.begin()

        # Set cancellation flag before processing
        await cancellation_flag.set_cancellation(job_id, reason="test")

        # Process the job - pass connection
        result = await worker.process_job(job_id, {"seed_url": job.seed_url}, conn=db_connection)

        # Verify job was acknowledged (not requeued)
        assert result is True

        # Commit worker transaction
        await transaction.commit()

        # Clean up
        await cancellation_flag.clear_cancellation(job_id)

    async def test_worker_handles_invalid_config(
        self,
        worker: CrawlJobWorker,
        db_connection: AsyncConnection,
    ) -> None:
        """Test worker handles jobs with invalid configuration."""
        # Create a job with invalid config (no steps)
        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create_seed_url_submission(
            seed_url="https://example.com/invalid",
            inline_config={"steps": [], "global_config": {}},  # Empty steps
            variables=None,
            job_type="one_time",
            priority=5,
            scheduled_at=None,
            max_retries=3,
            metadata=None,
        )

        assert job is not None
        job_id = str(job.id)

        # Commit the job
        await db_connection.commit()
        # Start new transaction for worker processing
        transaction = await db_connection.begin()

        # Process the job - pass connection
        result = await worker.process_job(job_id, {"seed_url": job.seed_url}, conn=db_connection)

        # Verify job was marked as failed
        assert result is True

        # Commit worker changes
        await transaction.commit()

        # Start new transaction for verification
        transaction = await db_connection.begin()

        # Verify job status was updated
        updated_job = await job_repo.get_by_id(job_id)
        assert updated_job is not None
        assert updated_job.status.value == "failed"
        assert "Invalid job configuration" in (updated_job.error_message or "")

        # Commit verification transaction
        await transaction.commit()

    async def test_worker_handles_404_response(
        self,
        worker: CrawlJobWorker,
        db_connection: AsyncConnection,
    ) -> None:
        """Test worker handles 404 responses appropriately."""
        # Create a job
        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create_seed_url_submission(
            seed_url="https://example.com/notfound",
            inline_config={
                "steps": [
                    {
                        "name": "test_step",
                        "type": "crawl",
                        "method": "http",
                        "config": {"url": "https://example.com/notfound"},
                        "selectors": {"detail_urls": "a"},
                    }
                ],
                "global_config": {},
            },
            variables=None,
            job_type="one_time",
            priority=5,
            scheduled_at=None,
            max_retries=3,
            metadata=None,
        )

        assert job is not None
        job_id = str(job.id)

        # Commit the job
        await db_connection.commit()
        # Start new transaction for worker processing
        transaction = await db_connection.begin()

        # Mock 404 response
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status_code = 404
            mock_response.text = "Not Found"
            mock_request.return_value = mock_response

            # Process the job - pass connection
            result = await worker.process_job(
                job_id, {"seed_url": job.seed_url}, conn=db_connection
            )

            # Verify job was marked as failed
            assert result is True

            # Commit worker changes
            await transaction.commit()

            # Start new transaction for verification
            transaction = await db_connection.begin()

            # Verify job status was updated
            updated_job = await job_repo.get_by_id(job_id)
            assert updated_job is not None
            assert updated_job.status.value == "failed"

            # Commit verification transaction
            await transaction.commit()
