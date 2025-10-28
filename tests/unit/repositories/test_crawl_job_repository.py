"""Unit tests for CrawlJobRepository."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import CrawlJob, JobTypeEnum, StatusEnum
from crawler.db.repositories.crawl_job import CrawlJobRepository


@pytest.mark.asyncio
class TestCrawlJobRepository:
    """Unit tests for CrawlJobRepository."""

    async def test_initialization(self):
        """Test repository initializes correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        assert repo.conn == mock_conn
        assert repo._querier is not None

    async def test_create_with_website_id(self):
        """Test create with website_id (template-based job)."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=uuid4(),
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config=None,
            status=StatusEnum.PENDING,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_job = AsyncMock(return_value=mock_job)

        website_id_str = "550e8400-e29b-41d4-a716-446655440000"
        result = await repo.create(seed_url="https://example.com", website_id=website_id_str)

        # Verify website_id was converted to UUID
        called_args = repo._querier.create_crawl_job.call_args
        assert isinstance(called_args.kwargs["website_id"], UUID)
        assert str(called_args.kwargs["website_id"]) == website_id_str
        assert called_args.kwargs["inline_config"] is None
        assert result == mock_job

    async def test_create_with_inline_config(self):
        """Test create with inline_config (no template)."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config={"method": "api"},
            status=StatusEnum.PENDING,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_job = AsyncMock(return_value=mock_job)

        inline_config = {"method": "api", "max_depth": 5}
        result = await repo.create(seed_url="https://example.com", inline_config=inline_config)

        # Verify inline_config was JSON serialized
        called_args = repo._querier.create_crawl_job.call_args
        assert called_args.kwargs["website_id"] is None
        assert called_args.kwargs["inline_config"] == json.dumps(inline_config)
        assert result == mock_job

    async def test_create_with_neither_website_id_nor_inline_config(self):
        """Test create with neither website_id nor inline_config passes both as None."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config=None,
            status=StatusEnum.PENDING,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_job = AsyncMock(return_value=mock_job)

        result = await repo.create(seed_url="https://example.com")

        # Verify both are None
        called_args = repo._querier.create_crawl_job.call_args
        assert called_args.kwargs["website_id"] is None
        assert called_args.kwargs["inline_config"] is None
        assert result == mock_job

    async def test_create_serializes_metadata_and_variables(self):
        """Test that create serializes metadata and variables to JSON."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config=None,
            status=StatusEnum.PENDING,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata={"key": "value"},
            variables={"var1": "val1"},
            progress=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_job = AsyncMock(return_value=mock_job)

        metadata = {"source": "api", "user_id": 123}
        variables = {"api_key": "secret", "region": "us-west"}
        result = await repo.create(
            seed_url="https://example.com", metadata=metadata, variables=variables
        )

        # Verify JSON serialization
        called_args = repo._querier.create_crawl_job.call_args
        assert called_args.kwargs["metadata"] == json.dumps(metadata)
        assert called_args.kwargs["variables"] == json.dumps(variables)
        assert result == mock_job

    async def test_update_progress_serializes_progress_dict(self):
        """Test that update_progress serializes progress dict to JSON."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config=None,
            status=StatusEnum.RUNNING,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress={"pages_crawled": 10},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.update_crawl_job_progress = AsyncMock(return_value=mock_job)

        job_id = uuid4()
        progress = {"pages_crawled": 10, "pages_queued": 5}
        result = await repo.update_progress(job_id=job_id, progress=progress)

        # Verify progress was JSON serialized
        called_args = repo._querier.update_crawl_job_progress.call_args
        assert called_args.kwargs["progress"] == json.dumps(progress)
        assert result == mock_job

    async def test_create_seed_url_submission_requires_inline_config(self):
        """Test create_seed_url_submission always serializes inline_config."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config={"method": "browser"},
            status=StatusEnum.PENDING,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_seed_url_submission = AsyncMock(return_value=mock_job)

        inline_config = {"method": "browser", "wait_for": "body"}
        result = await repo.create_seed_url_submission(
            seed_url="https://example.com", inline_config=inline_config
        )

        # Verify inline_config was JSON serialized (required, not optional)
        called_args = repo._querier.create_seed_url_submission.call_args
        assert called_args.kwargs["inline_config"] == json.dumps(inline_config)
        assert result == mock_job

    async def test_create_template_based_job_requires_website_id(self):
        """Test create_template_based_job converts website_id to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=uuid4(),
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config=None,
            status=StatusEnum.PENDING,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_template_based_job = AsyncMock(return_value=mock_job)

        website_id_str = "550e8400-e29b-41d4-a716-446655440000"
        result = await repo.create_template_based_job(
            website_id=website_id_str, seed_url="https://example.com"
        )

        # Verify website_id was converted to UUID
        called_args = repo._querier.create_template_based_job.call_args
        assert isinstance(called_args.kwargs["website_id"], UUID)
        assert str(called_args.kwargs["website_id"]) == website_id_str
        assert result == mock_job

    async def test_get_pending_collects_async_generator(self):
        """Test get_pending collects all results from async generator."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        # Create mock jobs
        mock_jobs = [
            CrawlJob(
                id=uuid4(),
                website_id=None,
                job_type=JobTypeEnum.ONE_TIME,
                seed_url=f"https://example{i}.com",
                inline_config=None,
                status=StatusEnum.PENDING,
                priority=i,
                scheduled_at=None,
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                cancelled_by=None,
                cancellation_reason=None,
                error_message=None,
                retry_count=0,
                max_retries=3,
                metadata=None,
                variables=None,
                progress=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():
            for job in mock_jobs:
                yield job

        repo._querier.get_pending_jobs = MagicMock(return_value=mock_generator())

        result = await repo.get_pending(limit=10)

        assert len(result) == 3
        assert all(isinstance(j, CrawlJob) for j in result)
        assert result == mock_jobs

    async def test_cancel_passes_optional_parameters(self):
        """Test cancel handles optional parameters correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlJobRepository(mock_conn)

        mock_job = CrawlJob(
            id=uuid4(),
            website_id=None,
            job_type=JobTypeEnum.ONE_TIME,
            seed_url="https://example.com",
            inline_config=None,
            status=StatusEnum.CANCELLED,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=datetime.now(UTC),
            cancelled_by="user123",
            cancellation_reason="User requested",
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.cancel_crawl_job = AsyncMock(return_value=mock_job)

        job_id = uuid4()
        result = await repo.cancel(job_id=job_id, cancelled_by="user123", reason="User requested")

        # Verify parameters were passed correctly
        called_args = repo._querier.cancel_crawl_job.call_args
        assert called_args.kwargs["cancelled_by"] == "user123"
        assert called_args.kwargs["cancellation_reason"] == "User requested"
        assert result == mock_job
