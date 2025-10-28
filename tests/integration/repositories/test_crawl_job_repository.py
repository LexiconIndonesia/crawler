"""Integration tests for CrawlJobRepository.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.generated.models import JobTypeEnum, StatusEnum
from crawler.db.repositories import CrawlJobRepository, WebsiteRepository


@pytest.mark.asyncio
class TestCrawlJobRepository:
    """Tests for CrawlJobRepository."""

    async def test_create_and_get_job(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a crawl job."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        # Create website first
        website = await website_repo.create(
            name="job-test-site", base_url="https://test.com", config={}
        )

        # Create job
        job = await job_repo.create(
            seed_url="https://test.com/start",
            website_id=str(website.id),
            job_type=JobTypeEnum.ONE_TIME,
            priority=7,
            metadata={"source": "test"},
        )

        assert job.seed_url == "https://test.com/start"
        assert job.priority == 7
        assert job.status == StatusEnum.PENDING
        assert job.metadata == {"source": "test"}

        # Get by ID
        fetched = await job_repo.get_by_id(str(job.id))
        assert fetched is not None
        assert fetched.seed_url == "https://test.com/start"

    async def test_update_job_status(self, db_session: AsyncSession) -> None:
        """Test updating job status."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        website = await website_repo.create(
            name="status-test-site", base_url="https://test.com", config={}
        )
        job = await job_repo.create(seed_url="https://test.com", website_id=str(website.id))

        # Update to running
        updated = await job_repo.update_status(
            str(job.id), status=StatusEnum.RUNNING, started_at=datetime.now(UTC)
        )

        assert updated is not None
        assert updated.status == StatusEnum.RUNNING
        assert updated.started_at is not None

    async def test_get_pending_jobs(self, db_session: AsyncSession) -> None:
        """Test getting pending jobs ordered by priority."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        website = await website_repo.create(
            name="pending-test-site", base_url="https://test.com", config={}
        )

        # Create jobs with different priorities
        await job_repo.create(
            seed_url="https://test.com/low",
            website_id=str(website.id),
            priority=3,
        )
        await job_repo.create(
            seed_url="https://test.com/high",
            website_id=str(website.id),
            priority=9,
        )

        pending = await job_repo.get_pending(limit=10)
        assert len(pending) >= 2

        # First job should have highest priority
        assert pending[0].priority >= pending[1].priority

    async def test_create_seed_url_submission(self, db_session: AsyncSession) -> None:
        """Test creating a job with inline configuration (no website template)."""
        conn = await db_session.connection()
        job_repo = CrawlJobRepository(conn)

        # Create job with inline config
        inline_config = {
            "method": "browser",
            "max_depth": 2,
            "selectors": [{"name": "title", "selector": "h1"}],
        }

        job = await job_repo.create_seed_url_submission(
            seed_url="https://example.com",
            inline_config=inline_config,
            variables={"category": "electronics"},
            priority=7,
        )

        assert job is not None
        assert job.seed_url == "https://example.com"
        assert job.website_id is None  # No website template
        assert job.inline_config == inline_config
        assert job.variables == {"category": "electronics"}
        assert job.priority == 7
        assert job.status == StatusEnum.PENDING

    async def test_create_template_based_job(self, db_session: AsyncSession) -> None:
        """Test creating a job using website template configuration."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        # Create website template
        website = await website_repo.create(
            name="template-site",
            base_url="https://template.com",
            config={"max_depth": 5, "method": "api"},
        )

        # Create job using template
        job = await job_repo.create_template_based_job(
            website_id=str(website.id),
            seed_url="https://template.com/start",
            variables={"page": "1"},
            priority=6,
        )

        assert job is not None
        assert job.seed_url == "https://template.com/start"
        assert str(job.website_id) == str(website.id)
        assert job.inline_config is None  # Uses website template config
        assert job.variables == {"page": "1"}
        assert job.priority == 6

    async def test_get_inline_config_jobs(self, db_session: AsyncSession) -> None:
        """Test getting jobs with inline configuration."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        # Create a website for template-based job
        website = await website_repo.create(
            name="inline-test-site", base_url="https://test.com", config={}
        )

        # Create template-based job (should NOT be in results)
        await job_repo.create_template_based_job(
            website_id=str(website.id),
            seed_url="https://test.com/template",
        )

        # Create inline config jobs (should be in results)
        await job_repo.create_seed_url_submission(
            seed_url="https://example1.com",
            inline_config={"method": "browser"},
        )
        await job_repo.create_seed_url_submission(
            seed_url="https://example2.com",
            inline_config={"method": "api"},
        )

        # Get inline config jobs
        inline_jobs = await job_repo.get_inline_config_jobs(limit=10)

        assert len(inline_jobs) >= 2
        # All jobs should have inline_config and no website_id
        assert all(job.inline_config is not None for job in inline_jobs)
        assert all(job.website_id is None for job in inline_jobs)

    async def test_get_jobs_by_seed_url(self, db_session: AsyncSession) -> None:
        """Test getting jobs by seed URL."""
        conn = await db_session.connection()
        job_repo = CrawlJobRepository(conn)

        test_url = "https://unique-test-url.com/page"

        # Create multiple jobs with the same seed URL
        await job_repo.create_seed_url_submission(
            seed_url=test_url,
            inline_config={"method": "browser"},
        )
        await job_repo.create_seed_url_submission(
            seed_url=test_url,
            inline_config={"method": "api"},
        )

        # Get jobs by seed URL
        jobs = await job_repo.get_by_seed_url(test_url, limit=10)

        assert len(jobs) >= 2
        assert all(job.seed_url == test_url for job in jobs)

    async def test_mixed_job_creation(self, db_session: AsyncSession) -> None:
        """Test that both inline and template-based job creation work together."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        # Create website template
        website = await website_repo.create(
            name="mixed-test-site",
            base_url="https://mixed.com",
            config={"rate_limit": 100},
        )

        # Create inline config job
        inline_job = await job_repo.create(
            seed_url="https://inline-example.com",
            inline_config={"method": "browser", "timeout": 30},
        )

        # Create template-based job
        template_job = await job_repo.create(
            seed_url="https://template-example.com",
            website_id=str(website.id),
        )

        assert inline_job.website_id is None
        assert inline_job.inline_config is not None

        assert str(template_job.website_id) == str(website.id)
        assert template_job.inline_config is None
