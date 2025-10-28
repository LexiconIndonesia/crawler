"""Integration tests for ScheduledJobRepository.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.repositories import ScheduledJobRepository, WebsiteRepository


@pytest.mark.asyncio
class TestScheduledJobRepository:
    """Tests for ScheduledJobRepository."""

    async def test_create_and_get_scheduled_job(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a scheduled job."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        scheduled_job_repo = ScheduledJobRepository(conn)

        # Create website first
        website = await website_repo.create(
            name="scheduled-test-site", base_url="https://test.com", config={}
        )

        # Create scheduled job
        next_run = datetime.now(UTC)
        job = await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=next_run,
            is_active=True,
            job_config={"max_depth": 5},
        )

        assert job.cron_schedule == "0 0 * * *"
        assert job.is_active is True
        assert job.job_config == {"max_depth": 5}
        assert job.next_run_time == next_run
        assert job.last_run_time is None

        # Get by ID
        fetched = await scheduled_job_repo.get_by_id(str(job.id))
        assert fetched is not None
        assert fetched.cron_schedule == "0 0 * * *"

    async def test_get_scheduled_jobs_by_website(self, db_session: AsyncSession) -> None:
        """Test getting all scheduled jobs for a website."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        scheduled_job_repo = ScheduledJobRepository(conn)

        website = await website_repo.create(
            name="multi-schedule-site", base_url="https://test.com", config={}
        )

        # Create multiple scheduled jobs for the same website
        await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
        )
        await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 12 * * *",
            next_run_time=datetime.now(UTC),
        )

        jobs = await scheduled_job_repo.get_by_website_id(str(website.id))
        assert len(jobs) == 2

    async def test_get_due_jobs(self, db_session: AsyncSession) -> None:
        """Test getting jobs due for execution."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        scheduled_job_repo = ScheduledJobRepository(conn)

        website = await website_repo.create(
            name="due-jobs-site", base_url="https://test.com", config={}
        )

        # Create job that's due now
        past_time = datetime.now(UTC)
        await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=past_time,
            is_active=True,
        )

        # Create job that's not due yet
        future_time = datetime(2099, 1, 1, tzinfo=UTC)
        await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=future_time,
            is_active=True,
        )

        # Get jobs due now
        due_jobs = await scheduled_job_repo.get_due_jobs(cutoff_time=datetime.now(UTC), limit=10)

        assert len(due_jobs) >= 1
        assert all(job.next_run_time <= datetime.now(UTC) for job in due_jobs)

    async def test_update_scheduled_job(self, db_session: AsyncSession) -> None:
        """Test updating a scheduled job."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        scheduled_job_repo = ScheduledJobRepository(conn)

        website = await website_repo.create(
            name="update-schedule-site", base_url="https://test.com", config={}
        )
        job = await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
        )

        # Update job
        new_next_run = datetime(2025, 12, 1, tzinfo=UTC)
        updated = await scheduled_job_repo.update(
            str(job.id),
            cron_schedule="0 12 * * *",
            next_run_time=new_next_run,
        )

        assert updated is not None
        assert updated.cron_schedule == "0 12 * * *"
        assert updated.next_run_time == new_next_run

    async def test_toggle_scheduled_job_status(self, db_session: AsyncSession) -> None:
        """Test toggling scheduled job active status."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        scheduled_job_repo = ScheduledJobRepository(conn)

        website = await website_repo.create(
            name="toggle-status-site", base_url="https://test.com", config={}
        )
        job = await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            is_active=True,
        )

        # Toggle to inactive
        updated = await scheduled_job_repo.toggle_status(str(job.id), is_active=False)
        assert updated is not None
        assert updated.is_active is False

        # Toggle back to active
        updated = await scheduled_job_repo.toggle_status(str(job.id), is_active=True)
        assert updated is not None
        assert updated.is_active is True

    async def test_update_next_run(self, db_session: AsyncSession) -> None:
        """Test updating next run time after execution."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        scheduled_job_repo = ScheduledJobRepository(conn)

        website = await website_repo.create(
            name="next-run-site", base_url="https://test.com", config={}
        )
        job = await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
        )

        # Update next run time
        last_run = datetime.now(UTC)
        next_run = datetime(2025, 12, 1, tzinfo=UTC)
        updated = await scheduled_job_repo.update_next_run(
            str(job.id), next_run_time=next_run, last_run_time=last_run
        )

        assert updated is not None
        assert updated.next_run_time == next_run
        assert updated.last_run_time == last_run

    async def test_website_with_cron_schedule(self, db_session: AsyncSession) -> None:
        """Test that websites can have a default cron schedule."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)

        # Create website with cron_schedule
        website = await website_repo.create(
            name="cron-schedule-site",
            base_url="https://test.com",
            config={},
            cron_schedule="0 0 1,15 * *",
        )

        assert website.cron_schedule == "0 0 1,15 * *"

        # Create website without cron_schedule (should use default)
        website2 = await website_repo.create(
            name="default-cron-site", base_url="https://test2.com", config={}
        )

        # Should have the default bi-weekly schedule
        assert website2.cron_schedule == "0 0 1,15 * *"

    async def test_job_config_deserialization(self, db_session: AsyncSession) -> None:
        """Test that job_config is properly deserialized from JSON."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        scheduled_job_repo = ScheduledJobRepository(conn)

        website = await website_repo.create(
            name="config-test-site", base_url="https://test.com", config={}
        )

        # Create job with complex job_config
        complex_config = {
            "max_depth": 5,
            "timeout": 30,
            "user_agent": "CustomBot/1.0",
            "headers": {"Authorization": "Bearer token123"},
            "nested": {"key": "value", "list": [1, 2, 3]},
        }

        job = await scheduled_job_repo.create(
            website_id=str(website.id),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            job_config=complex_config,
        )

        assert job is not None
        # Verify job_config is a dict, not a JSON string
        assert isinstance(job.job_config, dict)
        assert job.job_config == complex_config
        assert job.job_config["max_depth"] == 5
        assert job.job_config["nested"]["list"] == [1, 2, 3]

        # Test get_by_id deserialization
        retrieved_job = await scheduled_job_repo.get_by_id(str(job.id))
        assert retrieved_job is not None
        assert isinstance(retrieved_job.job_config, dict)
        assert retrieved_job.job_config == complex_config

        # Test get_by_website_id deserialization
        jobs = await scheduled_job_repo.get_by_website_id(str(website.id))
        assert len(jobs) == 1
        assert isinstance(jobs[0].job_config, dict)
        assert jobs[0].job_config == complex_config

        # Test get_due_jobs deserialization
        due_jobs = await scheduled_job_repo.get_due_jobs(
            cutoff_time=datetime.now(UTC) + timedelta(hours=1), limit=10
        )
        assert len(due_jobs) >= 1
        assert any(j.id == job.id for j in due_jobs)
        matching_job = next(j for j in due_jobs if j.id == job.id)
        assert isinstance(matching_job.job_config, dict)
        assert matching_job.job_config == complex_config

        # Test list_active deserialization
        active_jobs = await scheduled_job_repo.list_active(limit=10)
        assert len(active_jobs) >= 1
        assert any(j.id == job.id for j in active_jobs)
        matching_job = next(j for j in active_jobs if j.id == job.id)
        assert isinstance(matching_job.job_config, dict)
        assert matching_job.job_config == complex_config
