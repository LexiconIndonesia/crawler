"""Unit tests for JobService (dependency injection)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid7

import pytest
from pydantic import AnyUrl

from crawler.api.generated import (
    CancelJobRequest,
    CrawlStep,
    CreateSeedJobInlineRequest,
    CreateSeedJobRequest,
    GlobalConfig,
    MethodEnum,
    RetryConfig,
    StepTypeEnum,
)
from crawler.api.generated import (
    StatusEnum as ApiStatusEnum,
)
from crawler.api.v1.services import JobService
from crawler.db.generated.models import CrawlJob, JobTypeEnum, StatusEnum, Website


class TestJobService:
    """Tests for JobService with mocked dependencies."""

    @pytest.fixture
    def mock_crawl_job_repo(self):
        """Create a mock crawl job repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_website_repo(self):
        """Create a mock website repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_cancellation_flag(self):
        """Create a mock job cancellation flag service."""
        return AsyncMock()

    @pytest.fixture
    def mock_nats_queue(self):
        """Create a mock NATS queue service."""
        return AsyncMock()

    @pytest.fixture
    def job_service(
        self, mock_crawl_job_repo, mock_website_repo, mock_cancellation_flag, mock_nats_queue
    ):
        """Create JobService with mocked dependencies."""
        return JobService(
            crawl_job_repo=mock_crawl_job_repo,
            website_repo=mock_website_repo,
            cancellation_flag=mock_cancellation_flag,
            nats_queue=mock_nats_queue,
        )

    @pytest.fixture
    def sample_website_id(self) -> UUID:
        """Create a sample website ID."""
        return uuid7()

    @pytest.fixture
    def sample_request(self, sample_website_id):
        """Create a sample seed job creation request."""
        return CreateSeedJobRequest(
            website_id=sample_website_id,
            seed_url=AnyUrl("https://example.com/articles/2025"),
            variables={"year": "2025", "category": "tech"},
            priority=7,
        )

    @pytest.fixture
    def mock_website(self, sample_website_id):
        """Create a mock website model."""
        return Website(
            id=sample_website_id,
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

    @pytest.fixture
    def mock_crawl_job(self, sample_website_id):
        """Create a mock crawl job model."""
        return CrawlJob(
            id=uuid7(),
            website_id=sample_website_id,
            seed_url="https://example.com/articles/2025",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.PENDING,
            priority=7,
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
            variables={"year": "2025", "category": "tech"},
            progress=None,
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    @pytest.mark.asyncio
    async def test_create_seed_job_success(
        self, job_service, sample_request, mock_website, mock_crawl_job
    ):
        """Test successful seed job creation with template loading."""
        # Arrange
        job_service.website_repo.get_by_id.return_value = mock_website
        job_service.crawl_job_repo.create_template_based_job.return_value = mock_crawl_job

        # Act
        result = await job_service.create_seed_job(sample_request)

        # Assert
        assert result.id == mock_crawl_job.id
        assert result.website_id == sample_request.website_id
        assert str(result.seed_url) == str(sample_request.seed_url)
        assert result.status.status == ApiStatusEnum.pending
        assert result.priority == 7
        assert result.variables == {"year": "2025", "category": "tech"}

        # Verify repository calls
        job_service.website_repo.get_by_id.assert_called_once_with(sample_request.website_id)
        job_service.crawl_job_repo.create_template_based_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_seed_job_website_not_found(self, job_service, sample_request):
        """Test seed job creation fails when website template not found."""
        # Arrange
        job_service.website_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await job_service.create_seed_job(sample_request)

        # Verify website was looked up but job was never created
        job_service.website_repo.get_by_id.assert_called_once_with(sample_request.website_id)
        job_service.crawl_job_repo.create_template_based_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_seed_job_inactive_website(
        self, job_service, sample_request, mock_website
    ):
        """Test seed job creation fails when website is inactive."""
        # Arrange
        mock_website.status = StatusEnum.INACTIVE
        job_service.website_repo.get_by_id.return_value = mock_website

        # Act & Assert
        with pytest.raises(ValueError, match="inactive and cannot be used"):
            await job_service.create_seed_job(sample_request)

        # Verify website status was checked but job was never created
        job_service.website_repo.get_by_id.assert_called_once_with(sample_request.website_id)
        job_service.crawl_job_repo.create_template_based_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_seed_job_creation_fails(self, job_service, sample_request, mock_website):
        """Test seed job creation fails when repository returns None."""
        # Arrange
        job_service.website_repo.get_by_id.return_value = mock_website
        job_service.crawl_job_repo.create_template_based_job.return_value = None

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to create crawl job"):
            await job_service.create_seed_job(sample_request)

        # Verify both repositories were called
        job_service.website_repo.get_by_id.assert_called_once()
        job_service.crawl_job_repo.create_template_based_job.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_seed_job_with_default_priority(
        self, job_service, sample_website_id, mock_website, mock_crawl_job
    ):
        """Test seed job creation uses default priority when not specified."""
        # Arrange
        # Create a request object without priority to test Pydantic's default value handling
        request_without_priority = CreateSeedJobRequest(
            website_id=sample_website_id,
            seed_url=AnyUrl("https://example.com/articles/2025"),
            variables={"year": "2025", "category": "tech"},
        )
        assert request_without_priority.priority == 5  # Verify Pydantic default

        mock_crawl_job.priority = 5  # Ensure mock job reflects default priority

        job_service.website_repo.get_by_id.return_value = mock_website
        job_service.crawl_job_repo.create_template_based_job.return_value = mock_crawl_job

        # Act
        result = await job_service.create_seed_job(request_without_priority)

        # Assert
        assert result.priority == 5  # Default priority applied

        # Verify repository was called with default priority
        call_kwargs = job_service.crawl_job_repo.create_template_based_job.call_args.kwargs
        assert call_kwargs["priority"] == 5

    @pytest.mark.asyncio
    async def test_create_seed_job_without_variables(
        self, job_service, sample_request, mock_website, mock_crawl_job
    ):
        """Test seed job creation without variables."""
        # Arrange
        sample_request.variables = None
        mock_crawl_job.variables = None

        job_service.website_repo.get_by_id.return_value = mock_website
        job_service.crawl_job_repo.create_template_based_job.return_value = mock_crawl_job

        # Act
        result = await job_service.create_seed_job(sample_request)

        # Assert
        assert result.variables is None

        # Verify repository was called with None variables
        call_kwargs = job_service.crawl_job_repo.create_template_based_job.call_args.kwargs
        assert call_kwargs["variables"] is None

    @pytest.mark.asyncio
    async def test_create_seed_job_inline_success(self, job_service):
        """Test successful inline config seed job creation."""
        # Arrange
        inline_request = CreateSeedJobInlineRequest(
            seed_url=AnyUrl("https://example.com/articles"),
            steps=[
                CrawlStep(
                    name="scrape_article",
                    type=StepTypeEnum.scrape,
                    method=MethodEnum.http,
                    selectors={"title": "h1.title", "content": ".article-body"},
                )
            ],
            global_config=GlobalConfig(),
            variables={"api_key": "test_key_123"},
            priority=7,
        )

        mock_inline_job = CrawlJob(
            id=uuid7(),
            website_id=None,  # Inline jobs have no website_id
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.PENDING,
            priority=7,
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
            variables={"api_key": "test_key_123"},
            progress=None,
            inline_config={"steps": [], "global_config": {}},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        job_service.crawl_job_repo.create_seed_url_submission.return_value = mock_inline_job

        # Act
        result = await job_service.create_seed_job_inline(inline_request)

        # Assert
        assert result.id == mock_inline_job.id
        assert result.website_id is None  # Inline jobs have no website_id
        assert str(result.seed_url) == str(inline_request.seed_url)
        assert result.status.status == ApiStatusEnum.pending
        assert result.priority == 7
        assert result.variables == {"api_key": "test_key_123"}

        # Verify repository was called correctly
        job_service.crawl_job_repo.create_seed_url_submission.assert_called_once()
        call_kwargs = job_service.crawl_job_repo.create_seed_url_submission.call_args.kwargs
        assert call_kwargs["seed_url"] == "https://example.com/articles"
        assert "inline_config" in call_kwargs
        assert call_kwargs["priority"] == 7

    @pytest.mark.asyncio
    async def test_create_seed_job_inline_with_default_priority(self, job_service):
        """Test inline config seed job creation uses default priority."""
        # Arrange
        inline_request = CreateSeedJobInlineRequest(
            seed_url=AnyUrl("https://example.com/articles"),
            steps=[
                CrawlStep(
                    name="scrape_article",
                    type=StepTypeEnum.scrape,
                    method=MethodEnum.http,
                    selectors={"title": "h1.title"},
                )
            ],
            # No explicit priority - should default to 5
        )

        assert inline_request.priority == 5  # Verify Pydantic default

        mock_inline_job = CrawlJob(
            id=uuid7(),
            website_id=None,
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
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
            inline_config={"steps": [], "global_config": {}},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        job_service.crawl_job_repo.create_seed_url_submission.return_value = mock_inline_job

        # Act
        result = await job_service.create_seed_job_inline(inline_request)

        # Assert
        assert result.priority == 5

        # Verify repository was called with default priority
        call_kwargs = job_service.crawl_job_repo.create_seed_url_submission.call_args.kwargs
        assert call_kwargs["priority"] == 5

    @pytest.mark.asyncio
    async def test_create_seed_job_inline_creation_fails(self, job_service):
        """Test inline config seed job creation fails when repository returns None."""
        # Arrange
        inline_request = CreateSeedJobInlineRequest(
            seed_url=AnyUrl("https://example.com/articles"),
            steps=[
                CrawlStep(
                    name="scrape_article",
                    type=StepTypeEnum.scrape,
                    method=MethodEnum.http,
                    selectors={"title": "h1.title"},
                )
            ],
        )

        job_service.crawl_job_repo.create_seed_url_submission.return_value = None

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to create crawl job"):
            await job_service.create_seed_job_inline(inline_request)

        # Verify repository was called
        job_service.crawl_job_repo.create_seed_url_submission.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_seed_job_inline_validates_steps(self):
        """Test that inline config request validates step names are unique."""
        # Arrange - Create request with duplicate step names
        with pytest.raises(ValueError, match="Step names must be unique"):
            CreateSeedJobInlineRequest(
                seed_url=AnyUrl("https://example.com/articles"),
                steps=[
                    CrawlStep(
                        name="duplicate_step",
                        type=StepTypeEnum.scrape,
                        method=MethodEnum.http,
                        selectors={"title": "h1.title"},
                    ),
                    CrawlStep(
                        name="duplicate_step",
                        type=StepTypeEnum.scrape,
                        method=MethodEnum.http,
                        selectors={"content": ".content"},
                    ),
                ],
            )

    @pytest.mark.asyncio
    async def test_create_seed_job_inline_with_custom_retry_config(self, job_service):
        """Test that inline config seed job uses max_attempts from global_config.retry."""
        # Arrange
        inline_request = CreateSeedJobInlineRequest(
            seed_url=AnyUrl("https://example.com/articles"),
            steps=[
                CrawlStep(
                    name="scrape_article",
                    type=StepTypeEnum.scrape,
                    method=MethodEnum.http,
                    selectors={"title": "h1.title"},
                )
            ],
            global_config=GlobalConfig(retry=RetryConfig(max_attempts=7)),
            priority=5,
        )

        mock_inline_job = CrawlJob(
            id=uuid7(),
            website_id=None,
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
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
            max_retries=7,  # Should use custom retry config
            metadata=None,
            variables=None,
            progress=None,
            inline_config={"steps": [], "global_config": {"retry": {"max_attempts": 7}}},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        job_service.crawl_job_repo.create_seed_url_submission.return_value = mock_inline_job

        # Act
        result = await job_service.create_seed_job_inline(inline_request)

        # Assert
        assert result.id == mock_inline_job.id

        # Verify repository was called with custom max_retries from global_config.retry.max_attempts
        call_kwargs = job_service.crawl_job_repo.create_seed_url_submission.call_args.kwargs
        assert call_kwargs["max_retries"] == 7

    @pytest.mark.asyncio
    async def test_create_seed_job_with_custom_retry_config(
        self, job_service, sample_website_id, mock_crawl_job
    ):
        """Test that template-based seed job uses max_attempts from website config."""
        # Arrange
        request = CreateSeedJobRequest(
            website_id=sample_website_id,
            seed_url=AnyUrl("https://example.com/articles/2025"),
            variables={"year": "2025"},
            priority=5,
        )

        mock_website_with_retry = Website(
            id=sample_website_id,
            name="Test Website",
            base_url="https://example.com",
            config={
                "global_config": {
                    "retry": {
                        "max_attempts": 5,
                        "backoff_strategy": "exponential",
                    }
                }
            },
            status=StatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        mock_crawl_job.max_retries = 5

        job_service.website_repo.get_by_id.return_value = mock_website_with_retry
        job_service.crawl_job_repo.create_template_based_job.return_value = mock_crawl_job

        # Act
        result = await job_service.create_seed_job(request)

        # Assert
        assert result.id == mock_crawl_job.id

        # Verify repository was called with max_retries from website config
        call_kwargs = job_service.crawl_job_repo.create_template_based_job.call_args.kwargs
        assert call_kwargs["max_retries"] == 5

    @pytest.mark.asyncio
    async def test_cancel_job_success(self, job_service):
        """Test successful job cancellation."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest(reason="User requested cancellation")

        mock_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.RUNNING,
            priority=5,
            scheduled_at=None,
            started_at=datetime.now(UTC),
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
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_cancelled_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.CANCELLED,
            priority=5,
            scheduled_at=None,
            started_at=datetime.now(UTC),
            completed_at=None,
            cancelled_at=datetime.now(UTC),
            cancelled_by=None,
            cancellation_reason="User requested cancellation",
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        job_service.crawl_job_repo.get_by_id.return_value = mock_job
        job_service.cancellation_flag.set_cancellation.return_value = True
        job_service.crawl_job_repo.cancel.return_value = mock_cancelled_job

        # Act
        result = await job_service.cancel_job(job_id, cancel_request)

        # Assert
        assert result.id == UUID(job_id)
        assert result.status.status == ApiStatusEnum.cancelled
        assert result.message == "Job cancellation initiated"
        assert result.cancelled_at is not None

        # Verify repository and service calls
        job_service.crawl_job_repo.get_by_id.assert_called_once_with(job_id)
        job_service.cancellation_flag.set_cancellation.assert_called_once_with(
            job_id=job_id,
            reason="User requested cancellation",
        )
        job_service.crawl_job_repo.cancel.assert_called_once_with(
            job_id=job_id,
            cancelled_by=None,
            reason="User requested cancellation",
        )

    @pytest.mark.asyncio
    async def test_cancel_job_not_found(self, job_service):
        """Test job cancellation fails when job not found."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest(reason="User requested cancellation")
        job_service.crawl_job_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await job_service.cancel_job(job_id, cancel_request)

        # Verify repository lookup but no cancellation
        job_service.crawl_job_repo.get_by_id.assert_called_once_with(job_id)
        job_service.cancellation_flag.set_cancellation.assert_not_called()
        job_service.crawl_job_repo.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_job_already_cancelled(self, job_service):
        """Test job cancellation is idempotent when job is already cancelled."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest(reason="User requested cancellation")

        cancelled_at = datetime.now(UTC)
        mock_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.CANCELLED,  # Already cancelled
            priority=5,
            scheduled_at=None,
            started_at=datetime.now(UTC),
            completed_at=None,
            cancelled_at=cancelled_at,
            cancelled_by="admin",
            cancellation_reason="Previous cancellation",
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock the behavior: first get returns cancelled job, cancel returns None (no update),
        # second get returns same cancelled job
        job_service.crawl_job_repo.get_by_id.return_value = mock_job
        job_service.cancellation_flag.set_cancellation.return_value = True
        job_service.crawl_job_repo.cancel.return_value = None  # No rows updated

        # Act
        response = await job_service.cancel_job(job_id, cancel_request)

        # Assert - should succeed idempotently
        assert response.id == UUID(job_id)
        assert response.status.status == ApiStatusEnum.cancelled
        assert response.message == "Job is already cancelled"
        assert response.cancelled_at == cancelled_at

        # Verify the call sequence
        assert job_service.crawl_job_repo.get_by_id.call_count == 2  # Initial check + re-check
        job_service.cancellation_flag.set_cancellation.assert_called_once()
        job_service.crawl_job_repo.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cancel_job_already_completed(self, job_service):
        """Test job cancellation fails when job is already completed."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest(reason="User requested cancellation")

        mock_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.COMPLETED,  # Already completed
            priority=5,
            scheduled_at=None,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock: first get returns completed job, cancel returns None (no update due to status),
        # second get returns same completed job
        job_service.crawl_job_repo.get_by_id.return_value = mock_job
        job_service.cancellation_flag.set_cancellation.return_value = True
        job_service.crawl_job_repo.cancel.return_value = None  # No rows updated

        # Act & Assert
        with pytest.raises(ValueError, match="already completed and cannot be cancelled"):
            await job_service.cancel_job(job_id, cancel_request)

        # Verify the atomic behavior
        assert job_service.crawl_job_repo.get_by_id.call_count == 2  # Initial check + re-check
        job_service.cancellation_flag.set_cancellation.assert_called_once()
        job_service.crawl_job_repo.cancel.assert_called_once()
        job_service.cancellation_flag.clear_cancellation.assert_called_once_with(job_id)

    @pytest.mark.asyncio
    async def test_cancel_job_already_failed(self, job_service):
        """Test job cancellation fails when job is already failed."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest(reason="User requested cancellation")

        mock_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.FAILED,  # Already failed
            priority=5,
            scheduled_at=None,
            started_at=datetime.now(UTC),
            completed_at=datetime.now(UTC),
            cancelled_at=None,
            cancelled_by=None,
            cancellation_reason=None,
            error_message="Job failed due to timeout",
            retry_count=3,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock: first get returns failed job, cancel returns None (no update due to status),
        # second get returns same failed job
        job_service.crawl_job_repo.get_by_id.return_value = mock_job
        job_service.cancellation_flag.set_cancellation.return_value = True
        job_service.crawl_job_repo.cancel.return_value = None  # No rows updated

        # Act & Assert
        with pytest.raises(ValueError, match="already failed and cannot be cancelled"):
            await job_service.cancel_job(job_id, cancel_request)

        # Verify the atomic behavior
        assert job_service.crawl_job_repo.get_by_id.call_count == 2  # Initial check + re-check
        job_service.cancellation_flag.set_cancellation.assert_called_once()
        job_service.crawl_job_repo.cancel.assert_called_once()
        job_service.cancellation_flag.clear_cancellation.assert_called_once_with(job_id)

    @pytest.mark.asyncio
    async def test_cancel_job_redis_flag_fails(self, job_service):
        """Test job cancellation fails when Redis flag cannot be set."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest(reason="User requested cancellation")

        mock_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.RUNNING,
            priority=5,
            scheduled_at=None,
            started_at=datetime.now(UTC),
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
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        job_service.crawl_job_repo.get_by_id.return_value = mock_job
        job_service.cancellation_flag.set_cancellation.return_value = False  # Redis fails

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to set cancellation flag in Redis"):
            await job_service.cancel_job(job_id, cancel_request)

        # Verify Redis flag was attempted but DB cancel was not called
        job_service.crawl_job_repo.get_by_id.assert_called_once_with(job_id)
        job_service.cancellation_flag.set_cancellation.assert_called_once()
        job_service.crawl_job_repo.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_cancel_job_disappears(self, job_service):
        """Test job cancellation fails when job is deleted mid-operation."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest(reason="User requested cancellation")

        mock_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.RUNNING,
            priority=5,
            scheduled_at=None,
            started_at=datetime.now(UTC),
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
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Mock: first get succeeds, cancel returns None (job deleted), second get returns None
        job_service.crawl_job_repo.get_by_id.side_effect = [mock_job, None]
        job_service.cancellation_flag.set_cancellation.return_value = True
        job_service.crawl_job_repo.cancel.return_value = None  # Job was deleted

        # Act & Assert
        with pytest.raises(RuntimeError, match="no longer exists"):
            await job_service.cancel_job(job_id, cancel_request)

        # Verify Redis flag cleanup was called
        assert job_service.crawl_job_repo.get_by_id.call_count == 2
        job_service.cancellation_flag.set_cancellation.assert_called_once()
        job_service.crawl_job_repo.cancel.assert_called_once()
        job_service.cancellation_flag.clear_cancellation.assert_called_once_with(job_id)

    @pytest.mark.asyncio
    async def test_cancel_job_without_reason(self, job_service):
        """Test successful job cancellation without providing a reason."""
        # Arrange
        job_id = str(uuid7())
        cancel_request = CancelJobRequest()  # No reason provided

        mock_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
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
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        mock_cancelled_job = CrawlJob(
            id=UUID(job_id),
            website_id=uuid7(),
            seed_url="https://example.com/articles",
            job_type=JobTypeEnum.ONE_TIME,
            status=StatusEnum.CANCELLED,
            priority=5,
            scheduled_at=None,
            started_at=None,
            completed_at=None,
            cancelled_at=datetime.now(UTC),
            cancelled_by=None,
            cancellation_reason=None,
            error_message=None,
            retry_count=0,
            max_retries=3,
            metadata=None,
            variables=None,
            progress=None,
            inline_config=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        job_service.crawl_job_repo.get_by_id.return_value = mock_job
        job_service.cancellation_flag.set_cancellation.return_value = True
        job_service.crawl_job_repo.cancel.return_value = mock_cancelled_job

        # Act
        result = await job_service.cancel_job(job_id, cancel_request)

        # Assert
        assert result.id == UUID(job_id)
        assert result.status.status == ApiStatusEnum.cancelled

        # Verify cancellation was called with None reason
        job_service.cancellation_flag.set_cancellation.assert_called_once_with(
            job_id=job_id,
            reason=None,
        )
        job_service.crawl_job_repo.cancel.assert_called_once_with(
            job_id=job_id,
            cancelled_by=None,
            reason=None,
        )
