"""Unit tests for WebsiteService (dependency injection)."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid7

import pytest

from crawler.api.generated import (
    CrawlStep,
    CreateWebsiteRequest,
    MethodEnum,
    StepTypeEnum,
    WebsiteStatus,
)
from crawler.api.v1.services import WebsiteService
from crawler.db.generated.models import StatusEnum as DbStatusEnum
from crawler.db.generated.models import Website
from crawler.services.nats_queue import NATSQueueService


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
    def mock_config_history_repo(self):
        """Create a mock config history repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_crawl_job_repo(self):
        """Create a mock crawl job repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_nats_queue(self):
        """Create a mock NATS queue service with spec for type safety."""
        return AsyncMock(spec=NATSQueueService)

    @pytest.fixture
    def website_service(
        self,
        mock_website_repo,
        mock_scheduled_job_repo,
        mock_config_history_repo,
        mock_crawl_job_repo,
        mock_nats_queue,
    ):
        """Create WebsiteService with mocked dependencies."""
        return WebsiteService(
            website_repo=mock_website_repo,
            scheduled_job_repo=mock_scheduled_job_repo,
            config_history_repo=mock_config_history_repo,
            crawl_job_repo=mock_crawl_job_repo,
            nats_queue=mock_nats_queue,
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
    async def test_create_website_success(self, website_service, sample_request) -> None:
        """Test successful website creation."""
        # Arrange
        next_run_time = datetime.now(UTC)

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        mock_sched_job = MagicMock()
        mock_sched_job.id = uuid7()

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
        assert result.status == WebsiteStatus.active
        website_service.website_repo.get_by_name.assert_called_once_with("Test Website")
        website_service.website_repo.create.assert_called_once()
        website_service.scheduled_job_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_website_duplicate_name(self, website_service, sample_request) -> None:
        """Test website creation fails with duplicate name."""
        # Arrange
        next_run_time = datetime.now(UTC)

        existing_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_name.return_value = existing_website

        # Act & Assert
        with pytest.raises(ValueError, match="already exists"):
            await website_service.create_website(sample_request, next_run_time)

        website_service.website_repo.get_by_name.assert_called_once_with("Test Website")
        website_service.website_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_create_website_creation_fails(self, website_service, sample_request) -> None:
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
    async def test_create_website_without_schedule(self, website_service, sample_request) -> None:
        """Test website creation without scheduled job."""
        # Arrange
        sample_request.schedule.enabled = False
        next_run_time = datetime.now(UTC)

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_name.return_value = None
        website_service.website_repo.create.return_value = mock_website

        # Act
        result = await website_service.create_website(sample_request, next_run_time)

        # Assert
        assert result.scheduled_job_id is None
        assert result.next_run_time is None
        website_service.scheduled_job_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_website_by_id_success(self, website_service) -> None:
        """Test successful website retrieval with statistics."""
        # Arrange
        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        # Mock statistics
        mock_stats = MagicMock()
        mock_stats.total_jobs = 15
        mock_stats.completed_jobs = 12
        mock_stats.failed_jobs = 2
        mock_stats.cancelled_jobs = 1
        mock_stats.success_rate = 80.0
        mock_stats.total_pages_crawled = 1250
        mock_stats.last_crawl_at = datetime.now(UTC)

        # Mock scheduled job
        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.is_active = True
        mock_scheduled_job.next_run_time = datetime.now(UTC)

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.website_repo.get_statistics.return_value = mock_stats
        website_service.scheduled_job_repo.get_by_website_id.return_value = [mock_scheduled_job]

        # Act
        result = await website_service.get_website_by_id(website_id)

        # Assert
        assert result.name == "Test Website"
        assert result.statistics.total_jobs == 15
        assert result.statistics.completed_jobs == 12
        assert result.statistics.success_rate == 80.0
        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.website_repo.get_statistics.assert_called_once_with(website_id)

    @pytest.mark.asyncio
    async def test_get_website_by_id_not_found(self, website_service) -> None:
        """Test website retrieval fails when website not found."""
        # Arrange
        website_id = str(uuid7())
        website_service.website_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await website_service.get_website_by_id(website_id)

        website_service.website_repo.get_by_id.assert_called_once_with(website_id)

    @pytest.mark.asyncio
    async def test_get_website_by_id_no_statistics(self, website_service) -> None:
        """Test website retrieval with no statistics (no jobs run yet)."""
        # Arrange
        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.website_repo.get_statistics.return_value = None  # No stats
        website_service.scheduled_job_repo.get_by_website_id.return_value = []

        # Act
        result = await website_service.get_website_by_id(website_id)

        # Assert
        assert result.name == "Test Website"
        assert result.statistics.total_jobs == 0
        assert result.statistics.completed_jobs == 0
        assert result.statistics.success_rate == 0.0
        assert result.statistics.total_pages_crawled == 0
        assert result.statistics.last_crawl_at is None

    @pytest.mark.asyncio
    async def test_list_websites_success(self, website_service) -> None:
        """Test successful website listing."""
        # Arrange
        mock_websites = [
            Website(
                id=uuid7(),
                name="Website 1",
                base_url="https://example1.com",
                config={},
                status=DbStatusEnum.ACTIVE,
                cron_schedule="0 0 * * *",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                created_by=None,
                deleted_at=None,
            ),
            Website(
                id=uuid7(),
                name="Website 2",
                base_url="https://example2.com",
                config={},
                status=DbStatusEnum.ACTIVE,
                cron_schedule="0 0 * * *",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                created_by=None,
                deleted_at=None,
            ),
        ]

        website_service.website_repo.list.return_value = mock_websites
        website_service.website_repo.count.return_value = 2

        # Act
        result = await website_service.list_websites(status="active", limit=20, offset=0)

        # Assert
        assert len(result.websites) == 2
        assert result.total == 2
        assert result.limit == 20
        assert result.offset == 0
        assert result.websites[0].name == "Website 1"
        assert result.websites[1].name == "Website 2"

    @pytest.mark.asyncio
    async def test_list_websites_invalid_status(self, website_service) -> None:
        """Test website listing fails with invalid status."""
        # Act & Assert
        with pytest.raises(ValueError, match="Invalid status value"):
            await website_service.list_websites(status="invalid_status", limit=20, offset=0)

    @pytest.mark.asyncio
    async def test_update_website_success(self, website_service) -> None:
        """Test successful website update with versioning."""
        # Arrange
        from crawler.api.generated import UpdateWebsiteRequest

        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Original Name",
            base_url="https://example.com",
            config={"steps": [{"name": "old_step"}]},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        updated_website = Website(
            id=mock_website.id,
            name="Updated Name",
            base_url="https://example.com",
            config={"steps": [{"name": "new_step"}]},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=mock_website.created_at,
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.website_repo.get_by_name.return_value = None  # No duplicate
        website_service.config_history_repo.get_latest_version.return_value = 2
        website_service.website_repo.update.return_value = updated_website
        website_service.scheduled_job_repo.get_by_website_id.return_value = []

        request = UpdateWebsiteRequest(name="Updated Name", change_reason="Testing update")

        # Act
        result = await website_service.update_website(website_id, request)

        # Assert
        assert result.name == "Updated Name"
        assert result.config_version == 3
        website_service.config_history_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_website_not_found(self, website_service) -> None:
        """Test update fails when website not found."""
        # Arrange
        from crawler.api.generated import UpdateWebsiteRequest

        website_id = str(uuid7())
        website_service.website_repo.get_by_id.return_value = None

        request = UpdateWebsiteRequest(name="New Name")

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await website_service.update_website(website_id, request)

    @pytest.mark.asyncio
    async def test_update_website_no_changes(self, website_service) -> None:
        """Test update fails when no changes provided."""
        # Arrange
        from crawler.api.generated import UpdateWebsiteRequest

        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_id.return_value = mock_website

        request = UpdateWebsiteRequest()  # No fields set

        # Act & Assert
        with pytest.raises(ValueError, match="No changes"):
            await website_service.update_website(website_id, request)

    @pytest.mark.asyncio
    async def test_update_website_with_recrawl(self, website_service) -> None:
        """Test update with re-crawl triggering."""
        # Arrange
        from crawler.api.generated import UpdateWebsiteRequest

        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test",
            base_url="https://example.com",
            config={"steps": []},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        updated_website = mock_website
        mock_job = MagicMock()
        mock_job.id = uuid7()

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.website_repo.get_by_name.return_value = None  # No duplicate
        website_service.config_history_repo.get_latest_version.return_value = 1
        website_service.website_repo.update.return_value = updated_website
        website_service.scheduled_job_repo.get_by_website_id.return_value = []
        website_service.crawl_job_repo.create.return_value = mock_job

        request = UpdateWebsiteRequest(name="Updated", trigger_recrawl=True)

        # Act
        result = await website_service.update_website(website_id, request)

        # Assert
        assert result.recrawl_job_id == mock_job.id
        website_service.crawl_job_repo.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_website_success(self, website_service) -> None:
        """Test successful website deletion with job cancellation."""
        # Arrange
        website_id = str(uuid7())
        w_id = uuid7()

        mock_website = Website(
            id=w_id,
            name="Test Website",
            base_url="https://example.com",
            config={"steps": []},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        # Mock active jobs
        mock_jobs = [
            MagicMock(id=uuid7(), status="pending"),
            MagicMock(id=uuid7(), status="running"),
        ]

        deleted_website = Website(
            id=w_id,
            name="Test Website",
            base_url="https://example.com",
            config={"steps": []},
            status=DbStatusEnum.INACTIVE,
            cron_schedule="0 0 * * *",
            created_at=mock_website.created_at,
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=datetime.now(UTC),
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.crawl_job_repo.get_active_by_website.return_value = mock_jobs
        website_service.crawl_job_repo.cancel.return_value = MagicMock(id=uuid7())
        website_service.config_history_repo.get_latest_version.return_value = 3
        website_service.config_history_repo.create.return_value = MagicMock(version=4)
        website_service.website_repo.soft_delete.return_value = deleted_website

        # Act
        result = await website_service.delete_website(website_id, delete_data=False)

        # Assert
        assert str(result.id) == str(w_id)
        assert result.name == "Test Website"
        assert result.cancelled_jobs == 2
        assert len(result.cancelled_job_ids) == 2
        assert result.config_archived_version == 4
        assert "deleted successfully" in result.message
        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.crawl_job_repo.get_active_by_website.assert_called_once_with(website_id)
        assert website_service.crawl_job_repo.cancel.call_count == 2
        website_service.config_history_repo.create.assert_called_once()
        website_service.website_repo.soft_delete.assert_called_once_with(website_id)

    @pytest.mark.asyncio
    async def test_delete_website_not_found(self, website_service) -> None:
        """Test deletion fails when website not found."""
        # Arrange
        website_id = str(uuid7())
        website_service.website_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await website_service.delete_website(website_id, delete_data=False)

        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.website_repo.soft_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_website_already_deleted(self, website_service) -> None:
        """Test deletion fails when website already deleted."""
        # Arrange
        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.INACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=datetime.now(UTC),  # Already deleted
        )

        website_service.website_repo.get_by_id.return_value = mock_website

        # Act & Assert
        with pytest.raises(ValueError, match="already deleted"):
            await website_service.delete_website(website_id, delete_data=False)

        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.website_repo.soft_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_website_no_active_jobs(self, website_service) -> None:
        """Test deletion with no active jobs to cancel."""
        # Arrange
        website_id = str(uuid7())
        w_id = uuid7()

        mock_website = Website(
            id=w_id,
            name="Test Website",
            base_url="https://example.com",
            config={"steps": []},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        deleted_website = Website(
            id=w_id,
            name="Test Website",
            base_url="https://example.com",
            config={"steps": []},
            status=DbStatusEnum.INACTIVE,
            cron_schedule="0 0 * * *",
            created_at=mock_website.created_at,
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=datetime.now(UTC),
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.crawl_job_repo.get_active_by_website.return_value = []  # No jobs
        website_service.config_history_repo.get_latest_version.return_value = 1
        website_service.config_history_repo.create.return_value = MagicMock(version=2)
        website_service.website_repo.soft_delete.return_value = deleted_website

        # Act
        result = await website_service.delete_website(website_id, delete_data=False)

        # Assert
        assert result.cancelled_jobs == 0
        assert result.cancelled_job_ids == []
        website_service.crawl_job_repo.cancel.assert_not_called()
        website_service.website_repo.soft_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_website_soft_delete_fails(self, website_service) -> None:
        """Test deletion fails when soft delete returns None."""
        # Arrange
        website_id = str(uuid7())
        w_id = uuid7()

        mock_website = Website(
            id=w_id,
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.crawl_job_repo.get_active_by_website.return_value = []
        website_service.config_history_repo.get_latest_version.return_value = 1
        website_service.config_history_repo.create.return_value = MagicMock(version=2)
        website_service.website_repo.soft_delete.return_value = None  # Simulate failure

        # Act & Assert
        with pytest.raises(RuntimeError, match="Failed to delete website"):
            await website_service.delete_website(website_id, delete_data=False)

        website_service.website_repo.soft_delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_website_clear_cron_schedule(self, website_service) -> None:
        """Test that cron schedule can be cleared by sending cron: null."""
        # Arrange
        from crawler.api.generated import ScheduleConfig, UpdateWebsiteRequest

        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={"schedule": {"cron": "0 0 * * *", "enabled": True}},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 * * *",  # Has existing cron schedule
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        updated_website = Website(
            id=mock_website.id,
            name="Test Website",
            base_url="https://example.com",
            config={"schedule": {"cron": None, "enabled": True}},
            status=DbStatusEnum.ACTIVE,
            cron_schedule=None,  # Cron schedule cleared
            created_at=mock_website.created_at,
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.config_history_repo.get_latest_version.return_value = 1
        website_service.website_repo.update.return_value = updated_website
        website_service.scheduled_job_repo.get_by_website_id.return_value = []

        # Mock the created scheduled job with a proper UUID
        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        website_service.scheduled_job_repo.create.return_value = mock_scheduled_job

        # Send schedule with cron: None to clear it
        request = UpdateWebsiteRequest(
            schedule=ScheduleConfig(cron=None, enabled=True),
            change_reason="Clearing cron schedule",
        )

        # Act
        result = await website_service.update_website(website_id, request)

        # Assert
        assert result.name == "Test Website"

        # Verify update was called with cron_schedule=None
        website_service.website_repo.update.assert_called_once()
        call_args = website_service.website_repo.update.call_args
        # cron_schedule parameter should be None (cleared)
        assert call_args.kwargs["cron_schedule"] is None

        # Verify config history was saved
        website_service.config_history_repo.create.assert_called_once()

        # Verify scheduled job was created with default cron since cron was cleared
        # but schedule.enabled is True
        website_service.scheduled_job_repo.create.assert_called_once()
        job_call_args = website_service.scheduled_job_repo.create.call_args
        # Should use default bi-weekly cron since new_cron is None
        assert job_call_args.kwargs["cron_schedule"] == "0 0 1,15 * *"

    @pytest.mark.asyncio
    async def test_pause_schedule_success(self, website_service) -> None:
        """Test successfully pausing a website schedule."""
        # Arrange
        website_id = str(uuid7())
        scheduled_job_id = uuid7()

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 1,15 * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = scheduled_job_id
        mock_scheduled_job.cron_schedule = "0 0 1,15 * *"
        mock_scheduled_job.last_run_time = datetime.now(UTC)

        mock_updated_job = MagicMock()
        mock_updated_job.id = scheduled_job_id
        mock_updated_job.cron_schedule = "0 0 1,15 * *"
        mock_updated_job.last_run_time = mock_scheduled_job.last_run_time
        mock_updated_job.is_active = False
        mock_updated_job.next_run_time = None

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.scheduled_job_repo.get_by_website_id.return_value = [mock_scheduled_job]
        website_service.scheduled_job_repo.toggle_status.return_value = mock_updated_job

        # Act
        result = await website_service.pause_schedule(website_id)

        # Assert
        assert result.is_active is False
        assert result.next_run_time is None  # No next run when paused
        assert result.scheduled_job_id == scheduled_job_id
        assert result.name == "Test Website"
        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.scheduled_job_repo.get_by_website_id.assert_called_once()
        website_service.scheduled_job_repo.toggle_status.assert_called_once_with(
            job_id=scheduled_job_id, is_active=False
        )

    @pytest.mark.asyncio
    async def test_pause_schedule_website_not_found(self, website_service) -> None:
        """Test pausing schedule fails when website not found."""
        # Arrange
        website_id = str(uuid7())
        website_service.website_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await website_service.pause_schedule(website_id)

        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.scheduled_job_repo.get_by_website_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_pause_schedule_no_scheduled_job(self, website_service) -> None:
        """Test pausing schedule fails when no scheduled job exists."""
        # Arrange
        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 1,15 * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.scheduled_job_repo.get_by_website_id.return_value = []

        # Act & Assert
        with pytest.raises(ValueError, match="No scheduled job found"):
            await website_service.pause_schedule(website_id)

        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.scheduled_job_repo.get_by_website_id.assert_called_once()
        # Guard: toggle_status should not be called when no scheduled job exists
        website_service.scheduled_job_repo.toggle_status.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_schedule_success(self, website_service) -> None:
        """Test successfully resuming a website schedule."""
        # Arrange
        website_id = str(uuid7())
        scheduled_job_id = uuid7()

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 1,15 * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = scheduled_job_id
        mock_scheduled_job.cron_schedule = "0 0 1,15 * *"
        mock_scheduled_job.timezone = "UTC"  # Explicit timezone to avoid MagicMock truthiness
        mock_scheduled_job.last_run_time = datetime.now(UTC)

        mock_updated_job = MagicMock()
        mock_updated_job.id = scheduled_job_id
        mock_updated_job.cron_schedule = "0 0 1,15 * *"
        mock_updated_job.last_run_time = mock_scheduled_job.last_run_time
        mock_updated_job.is_active = True
        mock_updated_job.next_run_time = datetime.now(UTC)

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.scheduled_job_repo.get_by_website_id.return_value = [mock_scheduled_job]
        website_service.scheduled_job_repo.update.return_value = mock_updated_job

        # Act
        result = await website_service.resume_schedule(website_id)

        # Assert
        assert result.is_active is True
        assert result.next_run_time is not None  # Should have next run time
        assert result.scheduled_job_id == scheduled_job_id
        assert result.name == "Test Website"
        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.scheduled_job_repo.get_by_website_id.assert_called_once()
        website_service.scheduled_job_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_schedule_website_not_found(self, website_service) -> None:
        """Test resuming schedule fails when website not found."""
        # Arrange
        website_id = str(uuid7())
        website_service.website_repo.get_by_id.return_value = None

        # Act & Assert
        with pytest.raises(ValueError, match="not found"):
            await website_service.resume_schedule(website_id)

        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.scheduled_job_repo.get_by_website_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_resume_schedule_no_scheduled_job(self, website_service) -> None:
        """Test resuming schedule fails when no scheduled job exists."""
        # Arrange
        website_id = str(uuid7())

        mock_website = Website(
            id=uuid7(),
            name="Test Website",
            base_url="https://example.com",
            config={},
            status=DbStatusEnum.ACTIVE,
            cron_schedule="0 0 1,15 * *",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
        )

        website_service.website_repo.get_by_id.return_value = mock_website
        website_service.scheduled_job_repo.get_by_website_id.return_value = []

        # Act & Assert
        with pytest.raises(ValueError, match="No scheduled job found"):
            await website_service.resume_schedule(website_id)

        website_service.website_repo.get_by_id.assert_called_once_with(website_id)
        website_service.scheduled_job_repo.get_by_website_id.assert_called_once()
