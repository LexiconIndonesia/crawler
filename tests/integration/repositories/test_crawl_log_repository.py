"""Integration tests for CrawlLogRepository.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.generated.models import LogLevelEnum
from crawler.db.repositories import CrawlJobRepository, CrawlLogRepository, WebsiteRepository


@pytest.mark.asyncio
class TestCrawlLogRepository:
    """Tests for CrawlLogRepository."""

    async def test_create_and_list_logs(self, db_session: AsyncSession) -> None:
        """Test creating and listing logs."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)
        log_repo = CrawlLogRepository(conn)

        website = await website_repo.create(
            name="log-test-site", base_url="https://test.com", config={}
        )
        job = await job_repo.create(seed_url="https://test.com", website_id=str(website.id))

        # Create logs
        await log_repo.create(
            job_id=str(job.id),
            website_id=str(website.id),
            message="Test info log",
            log_level=LogLevelEnum.INFO,
        )
        await log_repo.create(
            job_id=str(job.id),
            website_id=str(website.id),
            message="Test error log",
            log_level=LogLevelEnum.ERROR,
        )

        # List all logs
        all_logs = await log_repo.list_by_job(str(job.id), limit=10)
        assert len(all_logs) == 2

        # Get only errors
        errors = await log_repo.get_errors(str(job.id), limit=10)
        assert len(errors) >= 1
        assert all(log.log_level in [LogLevelEnum.ERROR, LogLevelEnum.CRITICAL] for log in errors)
