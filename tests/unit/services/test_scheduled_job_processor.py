"""Unit tests for scheduled job processor with missed schedule handling."""

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid7

import pytest

from crawler.db.generated.models import JobTypeEnum, StatusEnum
from crawler.services.scheduled_job_processor import (
    MAX_CATCHUP_DELAY,
    handle_missed_schedules,
)


class TestHandleMissedSchedules:
    """Tests for handle_missed_schedules function."""

    @pytest.fixture
    def mock_scheduled_job_repo(self):
        """Create mock scheduled job repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_crawl_job_repo(self):
        """Create mock crawl job repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_website_repo(self):
        """Create mock website repository."""
        return AsyncMock()

    @pytest.fixture
    def mock_nats_queue(self):
        """Create mock NATS queue service."""
        return AsyncMock()

    @pytest.fixture
    def mock_website(self):
        """Create mock website."""
        website = MagicMock()
        website.id = uuid7()
        website.name = "Test Website"
        website.base_url = "https://example.com"
        website.deleted_at = None
        return website

    @pytest.fixture
    def mock_crawl_job(self):
        """Create mock crawl job."""
        job = MagicMock()
        job.id = uuid7()
        job.website_id = uuid7()
        job.seed_url = "https://example.com"
        job.job_type = JobTypeEnum.SCHEDULED
        job.priority = 5
        return job

    @pytest.mark.asyncio
    async def test_no_missed_schedules(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
    ) -> None:
        """Test when there are no missed schedules."""
        # Arrange
        mock_scheduled_job_repo.get_due_jobs.return_value = []

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 0
        assert skipped == 0
        mock_scheduled_job_repo.get_due_jobs.assert_called_once()

    @pytest.mark.asyncio
    async def test_catchup_missed_schedule_within_1_hour(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
        mock_crawl_job,
    ) -> None:
        """Test catching up a schedule missed by less than 1 hour."""
        # Arrange
        now = datetime.now(UTC)
        missed_time = now - timedelta(minutes=30)  # 30 minutes ago

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = mock_website.id
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "0 * * * *"  # Every hour
        mock_scheduled_job.job_config = {}
        mock_scheduled_job.timezone = "UTC"

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = mock_website
        mock_crawl_job_repo.create_template_based_job.return_value = mock_crawl_job
        mock_nats_queue.publish_job.return_value = True

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 1
        assert skipped == 0
        mock_crawl_job_repo.create_template_based_job.assert_called_once()
        mock_nats_queue.publish_job.assert_called_once()
        mock_scheduled_job_repo.update_next_run.assert_called_once()

        # Verify job metadata includes catchup flag (boolean True, not string)
        call_kwargs = mock_crawl_job_repo.create_template_based_job.call_args.kwargs
        assert call_kwargs["metadata"]["catchup"] is True
        assert call_kwargs["metadata"]["missed_time"] == missed_time.isoformat()

    @pytest.mark.asyncio
    async def test_skip_missed_schedule_over_1_hour(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
    ) -> None:
        """Test skipping a schedule missed by more than 1 hour."""
        # Arrange
        now = datetime.now(UTC)
        missed_time = now - timedelta(hours=2)  # 2 hours ago (over threshold)

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = mock_website.id
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "0 * * * *"  # Every hour
        mock_scheduled_job.job_config = {}
        mock_scheduled_job.timezone = "UTC"
        mock_scheduled_job.last_run_time = missed_time - timedelta(hours=1)

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = mock_website

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 0
        assert skipped == 1
        mock_crawl_job_repo.create_template_based_job.assert_not_called()
        mock_nats_queue.publish_job.assert_not_called()
        mock_scheduled_job_repo.update_next_run.assert_called_once()

    @pytest.mark.asyncio
    async def test_catchup_just_under_threshold(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
        mock_crawl_job,
    ) -> None:
        """Test behavior when missed time is just under the 1 hour threshold."""
        # Arrange
        # Use fixed timestamp to avoid timing flakiness from datetime.now() drift
        fixed_now = datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
        # Just under 1 hour (59 minutes 59 seconds)
        missed_time = fixed_now - MAX_CATCHUP_DELAY + timedelta(seconds=1)

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = mock_website.id
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "0 * * * *"
        mock_scheduled_job.job_config = {}
        mock_scheduled_job.timezone = "UTC"

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = mock_website
        mock_crawl_job_repo.create_template_based_job.return_value = mock_crawl_job
        mock_nats_queue.publish_job.return_value = True

        # Act
        # Mock datetime.now() to return fixed time to avoid flakiness
        with patch("crawler.services.scheduled_job_processor.datetime") as mock_datetime:
            mock_datetime.now.return_value = fixed_now
            mock_datetime.side_effect = lambda *args, **kwargs: datetime(*args, **kwargs)

            caught_up, skipped = await handle_missed_schedules(
                mock_scheduled_job_repo,
                mock_crawl_job_repo,
                mock_website_repo,
                mock_nats_queue,
            )

        # Assert - should catch up (< 1 hour)
        assert caught_up == 1
        assert skipped == 0

    @pytest.mark.asyncio
    async def test_website_not_found_deactivates_job(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
    ) -> None:
        """Test that missing website deactivates the scheduled job."""
        # Arrange
        now = datetime.now(UTC)
        missed_time = now - timedelta(minutes=30)

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = uuid7()
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "0 * * * *"

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = None  # Website not found

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 0
        assert skipped == 0
        mock_scheduled_job_repo.toggle_status.assert_called_once_with(
            job_id=str(mock_scheduled_job.id), is_active=False
        )

    @pytest.mark.asyncio
    async def test_deleted_website_deactivates_job(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
    ) -> None:
        """Test that deleted website deactivates the scheduled job."""
        # Arrange
        now = datetime.now(UTC)
        missed_time = now - timedelta(minutes=30)

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = mock_website.id
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "0 * * * *"

        mock_website.deleted_at = datetime.now(UTC)  # Website is deleted

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = mock_website

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 0
        assert skipped == 0
        mock_scheduled_job_repo.toggle_status.assert_called_once_with(
            job_id=str(mock_scheduled_job.id), is_active=False
        )

    @pytest.mark.asyncio
    async def test_invalid_cron_deactivates_job(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
    ) -> None:
        """Test that invalid cron expression deactivates the job."""
        # Arrange
        now = datetime.now(UTC)
        missed_time = now - timedelta(minutes=30)

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = mock_website.id
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "invalid cron"  # Invalid cron
        mock_scheduled_job.job_config = {}
        mock_scheduled_job.timezone = "UTC"

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = mock_website

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 0
        assert skipped == 0
        mock_scheduled_job_repo.toggle_status.assert_called_once_with(
            job_id=str(mock_scheduled_job.id), is_active=False
        )

    @pytest.mark.asyncio
    async def test_job_creation_failure_continues_processing(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
    ) -> None:
        """Test that job creation failure doesn't stop processing other jobs."""
        # Arrange
        now = datetime.now(UTC)
        missed_time = now - timedelta(minutes=30)

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = mock_website.id
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "0 * * * *"
        mock_scheduled_job.job_config = {}
        mock_scheduled_job.timezone = "UTC"

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = mock_website
        mock_crawl_job_repo.create_template_based_job.return_value = None  # Creation failed

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 0
        assert skipped == 0
        mock_crawl_job_repo.create_template_based_job.assert_called_once()
        mock_nats_queue.publish_job.assert_not_called()

    @pytest.mark.asyncio
    async def test_publish_failure_marks_job_as_cancelled(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
        mock_crawl_job,
    ) -> None:
        """Test that publish failure marks the job as cancelled."""
        # Arrange
        now = datetime.now(UTC)
        missed_time = now - timedelta(minutes=30)

        mock_scheduled_job = MagicMock()
        mock_scheduled_job.id = uuid7()
        mock_scheduled_job.website_id = mock_website.id
        mock_scheduled_job.next_run_time = missed_time
        mock_scheduled_job.cron_schedule = "0 * * * *"
        mock_scheduled_job.job_config = {}
        mock_scheduled_job.timezone = "UTC"

        mock_scheduled_job_repo.get_due_jobs.return_value = [mock_scheduled_job]
        mock_website_repo.get_by_id.return_value = mock_website
        mock_crawl_job_repo.create_template_based_job.return_value = mock_crawl_job
        mock_nats_queue.publish_job.return_value = False  # Publish failed

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 0
        assert skipped == 0
        mock_crawl_job_repo.update_status.assert_called_once_with(
            job_id=str(mock_crawl_job.id), status=StatusEnum.CANCELLED
        )

    @pytest.mark.asyncio
    async def test_mixed_catchup_and_skip(
        self,
        mock_scheduled_job_repo,
        mock_crawl_job_repo,
        mock_website_repo,
        mock_nats_queue,
        mock_website,
        mock_crawl_job,
    ) -> None:
        """Test handling multiple jobs with mix of catch-up and skip."""
        # Arrange
        now = datetime.now(UTC)

        # Job 1: 30 minutes late (should catch up)
        job1 = MagicMock()
        job1.id = uuid7()
        job1.website_id = mock_website.id
        job1.next_run_time = now - timedelta(minutes=30)
        job1.cron_schedule = "0 * * * *"
        job1.job_config = {}
        job1.timezone = "UTC"

        # Job 2: 2 hours late (should skip)
        job2 = MagicMock()
        job2.id = uuid7()
        job2.website_id = mock_website.id
        job2.next_run_time = now - timedelta(hours=2)
        job2.cron_schedule = "0 * * * *"
        job2.job_config = {}
        job2.last_run_time = now - timedelta(hours=3)
        job2.timezone = "UTC"

        mock_scheduled_job_repo.get_due_jobs.return_value = [job1, job2]
        mock_website_repo.get_by_id.return_value = mock_website
        mock_crawl_job_repo.create_template_based_job.return_value = mock_crawl_job
        mock_nats_queue.publish_job.return_value = True

        # Act
        caught_up, skipped = await handle_missed_schedules(
            mock_scheduled_job_repo,
            mock_crawl_job_repo,
            mock_website_repo,
            mock_nats_queue,
        )

        # Assert
        assert caught_up == 1
        assert skipped == 1
        assert mock_crawl_job_repo.create_template_based_job.call_count == 1
        assert mock_scheduled_job_repo.update_next_run.call_count == 2
