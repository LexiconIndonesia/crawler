"""Unit tests for WebsiteService (dependency injection)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from crawler.api.schemas import StatusEnum
from crawler.api.v1.schemas import (
    CrawlStep,
    CreateWebsiteRequest,
    MethodEnum,
    StepTypeEnum,
)
from crawler.api.v1.services import WebsiteService
from crawler.db.generated.models import Website


class TestWebsiteService:
    """Tests for WebsiteService with mocked dependencies."""

    @pytest.fixture
    def mock_website_repo(self):
        """Create a mock website repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_scheduled_job_repo(self):
        """Create a mock scheduled job repository."""
        return AsyncMock()

    @pytest.fixture
    def website_service(self, mock_website_repo, mock_scheduled_job_repo):
        """Create WebsiteService with mocked dependencies."""
        return WebsiteService(
            website_repo=mock_website_repo,
            scheduled_job_repo=mock_scheduled_job_repo,
        )

    @pytest.fixture
    def sample_request(self):
        """Create a sample website creation request."""
        return CreateWebsiteRequest(
            name="Test Website",
            base_url="https://example.com",
            steps=[CrawlStep(name="test_step", type=StepTypeEnum.crawl, method=MethodEnum.api)],
        )

    @pytest.mark.asyncio
    async def test_create_website_success(self, website_service, sample_request):
        """Test successful website creation."""
        # Arrange
        next_run_time = datetime.now(UTC)

        mock_website = Website(
            id=uuid4(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=StatusEnum.active,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
        )

        mock_sched_job = MagicMock()
        mock_sched_job.id = uuid4()

        website_service.website_repo.get_by_name.return_value = None
        website_service.website_repo.create.return_value = mock_website
        website_service.scheduled_job_repo.create.return_value = mock_sched_job

        # Act
        result = await website_service.create_website(sample_request, next_run_time)

        # Assert
        assert result.name == "Test Website"
        assert (
            str(result.base_url) == "https://example.com/"
        )  # AnyUrl normalizes with trailing slash
        assert result.status == StatusEnum.active
        website_service.website_repo.get_by_name.assert_called_once_with("Test Website")
        website_service.website_repo.create.assert_called_once()
        website_service.scheduled_job_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_website_duplicate_name(self, website_service, sample_request):
        """Test website creation fails with duplicate name."""
        # Arrange
        next_run_time = datetime.now(UTC)

        existing_website = Website(
            id=uuid4(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=StatusEnum.active,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
        )

        website_service.website_repo.get_by_name.return_value = existing_website

        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            await website_service.create_website(sample_request, next_run_time)

        website_service.website_repo.get_by_name.assert_called_once_with("Test Website")
        website_service.website_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_website_creation_fails(self, website_service, sample_request):
        """Test website creation fails when repository returns None."""
        # Arrange
        next_run_time = datetime.now(UTC)

        website_service.website_repo.get_by_name.return_value = None
        website_service.website_repo.create.return_value = None  # Simulate failure

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to create website"):
            await website_service.create_website(sample_request, next_run_time)

        website_service.website_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_website_without_schedule(self, website_service, sample_request):
        """Test website creation without scheduled job."""
        # Arrange
        sample_request.schedule.enabled = False
        next_run_time = datetime.now(UTC)

        mock_website = Website(
            id=uuid4(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=StatusEnum.active,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
        )

        website_service.website_repo.get_by_name.return_value = None
        website_service.website_repo.create.return_value = mock_website

        # Act
        result = await website_service.create_website(sample_request, next_run_time)

        # Assert
        assert result.scheduled_job_id is None
        assert result.next_run_time is None
        website_service.scheduled_job_repo.create.assert_not_called()
