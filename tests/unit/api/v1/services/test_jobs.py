"""Unit tests for JobService (dependency injection)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import UUID, uuid7

import pytest
from pydantic import AnyUrl

from crawler.api.generated import (
    CrawlStep,
    CreateSeedJobInlineRequest,
    CreateSeedJobRequest,
    GlobalConfig,
    MethodEnum,
    StepTypeEnum,
)
from crawler.api.schemas import StatusEnum as ApiStatusEnum
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
    def job_service(self, mock_crawl_job_repo, mock_website_repo):
        """Create JobService with mocked dependencies."""
        return JobService(
            crawl_job_repo=mock_crawl_job_repo,
            website_repo=mock_website_repo,
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
        assert result.status == ApiStatusEnum.pending
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
        assert result.status == ApiStatusEnum.pending
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
