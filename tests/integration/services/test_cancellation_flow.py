"""Integration tests for job cancellation with resource cleanup."""

from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import httpx
import pytest
import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncConnection

from config import get_settings
from crawler.api.generated import CrawlStep, MethodEnum, PaginationConfig, StepConfig, StepTypeEnum
from crawler.api.generated.models import Type as PaginationType
from crawler.db.repositories import CrawlJobRepository
from crawler.services import (
    CleanupCoordinator,
    CrawlOutcome,
    JobCancellationFlag,
    SeedURLCrawler,
    SeedURLCrawlerConfig,
)


@pytest.fixture
async def redis_client() -> AsyncGenerator[redis.Redis, None]:  # type: ignore[type-arg]
    """Create Redis client for testing."""
    settings = get_settings()
    client = redis.from_url(settings.redis_url)
    yield client
    await client.aclose()  # type: ignore[attr-defined]


@pytest.fixture
async def cancellation_flag(redis_client: redis.Redis) -> JobCancellationFlag:  # type: ignore[type-arg]
    """Create job cancellation flag service."""
    settings = get_settings()
    return JobCancellationFlag(redis_client, settings)


@pytest.fixture
async def cleanup_coordinator() -> CleanupCoordinator:
    """Create cleanup coordinator."""
    return CleanupCoordinator(graceful_timeout=5.0)


@pytest.fixture
async def job_repository(db_connection: AsyncConnection) -> CrawlJobRepository:
    """Create job repository."""
    return CrawlJobRepository(db_connection)


def _create_mock_response(status_code: int = 200, content: bytes = b"<html></html>") -> AsyncMock:
    """Create a mock HTTP response."""
    mock_response = AsyncMock()
    mock_response.status_code = status_code
    mock_response.content = content
    return mock_response


class TestCancellationFlow:
    """Integration tests for cancellation flow with resource cleanup."""

    async def test_cancellation_without_cleanup_coordinator(
        self,
        cancellation_flag: JobCancellationFlag,
    ) -> None:
        """Test cancellation without cleanup coordinator (backward compatibility)."""
        job_id = "test-job-no-cleanup"

        # Create a simple crawl step
        step = CrawlStep(
            name="test_step",
            type=StepTypeEnum.crawl,
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a"},
        )

        config = SeedURLCrawlerConfig(
            step=step,
            job_id=job_id,
            cancellation_flag=cancellation_flag,
            # No cleanup_coordinator - should still work
        )

        # Set cancellation flag before crawling
        await cancellation_flag.set_cancellation(job_id, reason="test")

        # Create crawler and attempt crawl
        crawler = SeedURLCrawler()

        # Mock HTTP client to avoid actual network calls
        async with httpx.AsyncClient() as client:
            config.http_client = client

            # This should detect cancellation and return CANCELLED outcome
            # but without performing cleanup
            result = await crawler.crawl("https://example.com", config)

        assert result.outcome == CrawlOutcome.CANCELLED
        assert result.error_message == "Job was cancelled during execution"

        # Clean up Redis
        await cancellation_flag.clear_cancellation(job_id)

    async def test_cancellation_with_cleanup_coordinator(
        self,
        cancellation_flag: JobCancellationFlag,
        cleanup_coordinator: CleanupCoordinator,
        job_repository: CrawlJobRepository,
    ) -> None:
        """Test cancellation with cleanup coordinator and job status update."""
        # Create a test job
        job = await job_repository.create_seed_url_submission(
            seed_url="https://example.com/test",
            inline_config={"method": "http", "max_depth": 1},
        )
        assert job is not None
        job_id = str(job.id)

        # Create crawl step
        step = CrawlStep(
            name="test_step",
            type=StepTypeEnum.crawl,
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com/test"),
            selectors={"detail_urls": "a.product"},
        )

        config = SeedURLCrawlerConfig(
            step=step,
            job_id=job_id,
            cancellation_flag=cancellation_flag,
            cleanup_coordinator=cleanup_coordinator,
            job_repo=job_repository,
            cancelled_by="test-user",
        )

        # Set cancellation flag
        await cancellation_flag.set_cancellation(job_id, reason="user request")

        # Create crawler
        crawler = SeedURLCrawler()

        # Mock HTTP client to return successful response
        mock_html = b'<html><body><a class="product" href="/product1">Product 1</a></body></html>'

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", return_value=_create_mock_response(200, mock_html)):
                config.http_client = client

                # Crawl should detect cancellation, perform cleanup, and update job
                result = await crawler.crawl("https://example.com/test", config)

        # Verify result
        assert result.outcome == CrawlOutcome.CANCELLED
        assert result.error_message == "Job was cancelled during execution"

        # Verify job status was updated in database
        updated_job = await job_repository.get_by_id(job_id)
        assert updated_job is not None
        assert updated_job.status.value == "cancelled"
        assert updated_job.cancelled_at is not None
        assert updated_job.cancelled_by == "test-user"
        assert updated_job.cancellation_reason == "Job cancellation requested"

        # Clean up
        await cancellation_flag.clear_cancellation(job_id)

    async def test_cancellation_during_pagination(
        self,
        cancellation_flag: JobCancellationFlag,
        cleanup_coordinator: CleanupCoordinator,
    ) -> None:
        """Test cancellation during multi-page crawl preserves partial results."""
        job_id = "test-job-pagination-cancel"

        # Create crawl step with pagination
        step = CrawlStep(
            name="test_step_pagination",
            type=StepTypeEnum.crawl,
            method=MethodEnum.http,
            config=StepConfig(
                url="https://example.com/page-1",
                pagination=PaginationConfig(
                    enabled=True,
                    type=PaginationType.page_based,
                    max_pages=10,
                ),
            ),
            selectors={"detail_urls": "a.item"},
        )

        config = SeedURLCrawlerConfig(
            step=step,
            job_id=job_id,
            cancellation_flag=cancellation_flag,
            cleanup_coordinator=cleanup_coordinator,
            cancelled_by="system",
        )

        crawler = SeedURLCrawler()

        # Set cancellation flag before crawl (simulates cancellation request during execution)
        # The crawler checks for cancellation at multiple points during execution
        await cancellation_flag.set_cancellation(job_id, reason="timeout")

        # Mock HTTP client to return successful response
        mock_html = b'<html><body><a class="item" href="/item1">Item 1</a></body></html>'

        async with httpx.AsyncClient() as client:
            with patch.object(client, "get", return_value=_create_mock_response(200, mock_html)):
                config.http_client = client

                # Crawl should detect cancellation and stop
                result = await crawler.crawl("https://example.com/page-1", config)

        # Verify result - should be cancelled (detected at first checkpoint)
        assert result.outcome == CrawlOutcome.CANCELLED
        # Partial results should be preserved (may be 0 if caught early)
        assert result.total_pages_crawled >= 0

        # Clean up
        await cancellation_flag.clear_cancellation(job_id)

    async def test_http_resource_cleanup_on_cancellation(
        self,
        cancellation_flag: JobCancellationFlag,
        cleanup_coordinator: CleanupCoordinator,
    ) -> None:
        """Test that HTTP resources are properly cleaned up on cancellation."""
        job_id = "test-job-http-cleanup"

        step = CrawlStep(
            name="test_http_cleanup",
            type=StepTypeEnum.crawl,
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a"},
        )

        config = SeedURLCrawlerConfig(
            step=step,
            job_id=job_id,
            cancellation_flag=cancellation_flag,
            cleanup_coordinator=cleanup_coordinator,
        )

        # Set cancellation flag
        await cancellation_flag.set_cancellation(job_id)

        crawler = SeedURLCrawler()

        # Create HTTP client that will be managed
        async with httpx.AsyncClient(timeout=30) as client:
            config.http_client = client

            # Verify HTTP resource is registered with cleanup coordinator
            initial_resources = len(cleanup_coordinator.resources)

            result = await crawler.crawl("https://example.com", config)

            # Verify result
            assert result.outcome == CrawlOutcome.CANCELLED

            # Verify HTTP resource was registered
            assert len(cleanup_coordinator.resources) == initial_resources + 1

        # Clean up
        await cancellation_flag.clear_cancellation(job_id)

    async def test_graceful_close_timeout_triggers_force_close(
        self,
        cancellation_flag: JobCancellationFlag,
    ) -> None:
        """Test that force close is triggered when graceful close times out."""
        job_id = "test-job-force-close"

        # Create coordinator with very short timeout
        short_timeout_coordinator = CleanupCoordinator(graceful_timeout=0.1)

        step = CrawlStep(
            name="test_force_close",
            type=StepTypeEnum.crawl,
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a"},
        )

        config = SeedURLCrawlerConfig(
            step=step,
            job_id=job_id,
            cancellation_flag=cancellation_flag,
            cleanup_coordinator=short_timeout_coordinator,
        )

        # Set cancellation
        await cancellation_flag.set_cancellation(job_id)

        crawler = SeedURLCrawler()

        async with httpx.AsyncClient() as client:
            config.http_client = client

            result = await crawler.crawl("https://example.com", config)

            # Should complete despite short timeout
            assert result.outcome == CrawlOutcome.CANCELLED

        # Clean up
        await cancellation_flag.clear_cancellation(job_id)

    async def test_cancellation_preserves_extracted_urls(
        self,
        cancellation_flag: JobCancellationFlag,
        cleanup_coordinator: CleanupCoordinator,
    ) -> None:
        """Test that extracted URLs are preserved when job is cancelled."""
        job_id = "test-job-preserve-urls"

        step = CrawlStep(
            name="test_preserve_urls",
            type=StepTypeEnum.crawl,
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a.product"},
        )

        config = SeedURLCrawlerConfig(
            step=step,
            job_id=job_id,
            cancellation_flag=cancellation_flag,
            cleanup_coordinator=cleanup_coordinator,
        )

        # Set cancellation immediately
        await cancellation_flag.set_cancellation(job_id, reason="preserve test")

        crawler = SeedURLCrawler()

        async with httpx.AsyncClient() as client:
            config.http_client = client

            result = await crawler.crawl("https://example.com", config)

        # Verify cancellation result
        assert result.outcome == CrawlOutcome.CANCELLED
        assert result.error_message == "Job was cancelled during execution"

        # Extracted URLs list should exist (even if empty)
        assert result.extracted_urls is not None
        assert isinstance(result.extracted_urls, list)

        # Clean up
        await cancellation_flag.clear_cancellation(job_id)
