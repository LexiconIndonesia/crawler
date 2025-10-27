"""Integration tests for sqlc-generated repositories.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.repositories import (
    ContentHashRepository,
    CrawlJobRepository,
    CrawledPageRepository,
    CrawlLogRepository,
    WebsiteRepository,
)


@pytest.mark.asyncio
class TestWebsiteRepository:
    """Tests for WebsiteRepository."""

    async def test_create_and_get_website(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a website."""
        async with db_session.begin():
            repo = WebsiteRepository(await db_session.connection())

            # Create website
            website = await repo.create(
                name="test-site",
                base_url="https://example.com",
                config={"max_depth": 3},
                created_by="test@example.com",
            )

            assert website.name == "test-site"
            assert website.base_url == "https://example.com"
            assert website.config == {"max_depth": 3}
            assert website.created_by == "test@example.com"
            assert website.status.value == "active"

            # Get by ID
            fetched = await repo.get_by_id(str(website.id))
            assert fetched is not None
            assert fetched.name == "test-site"

            # Get by name
            fetched_by_name = await repo.get_by_name("test-site")
            assert fetched_by_name is not None
            assert str(fetched_by_name.id) == str(website.id)

    async def test_update_website(self, db_session: AsyncSession) -> None:
        """Test updating a website."""
        async with db_session.begin():
            repo = WebsiteRepository(await db_session.connection())

            website = await repo.create(
                name="update-test", base_url="https://example.com", config={}
            )

            updated = await repo.update(
                str(website.id), status="inactive", config={"new_field": "value"}
            )

            assert updated is not None
            assert updated.status.value == "inactive"
            assert updated.config == {"new_field": "value"}

    async def test_list_websites(self, db_session: AsyncSession) -> None:
        """Test listing websites."""
        async with db_session.begin():
            repo = WebsiteRepository(await db_session.connection())

            # Create multiple websites
            await repo.create(name="site1", base_url="https://site1.com", config={})
            await repo.create(name="site2", base_url="https://site2.com", config={})
            await repo.create(
                name="site3", base_url="https://site3.com", config={}, status="inactive"
            )

            # List all active
            active_sites = await repo.list(status="active", limit=10)
            assert len(active_sites) >= 2

            # Count
            count = await repo.count(status="active")
            assert count >= 2


@pytest.mark.asyncio
class TestCrawlJobRepository:
    """Tests for CrawlJobRepository."""

    async def test_create_and_get_job(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a crawl job."""
        async with db_session.begin():
            conn = await db_session.connection()
            website_repo = WebsiteRepository(conn)
            job_repo = CrawlJobRepository(conn)

            # Create website first
            website = await website_repo.create(
                name="job-test-site", base_url="https://test.com", config={}
            )

            # Create job
            job = await job_repo.create(
                website_id=str(website.id),
                seed_url="https://test.com/start",
                job_type="one_time",
                priority=7,
                metadata={"source": "test"},
            )

            assert job.seed_url == "https://test.com/start"
            assert job.priority == 7
            assert job.status.value == "pending"
            assert job.metadata == {"source": "test"}

            # Get by ID
            fetched = await job_repo.get_by_id(str(job.id))
            assert fetched is not None
            assert fetched.seed_url == "https://test.com/start"

    async def test_update_job_status(self, db_session: AsyncSession) -> None:
        """Test updating job status."""
        async with db_session.begin():
            conn = await db_session.connection()
            website_repo = WebsiteRepository(conn)
            job_repo = CrawlJobRepository(conn)

            website = await website_repo.create(
                name="status-test-site", base_url="https://test.com", config={}
            )
            job = await job_repo.create(
                website_id=str(website.id), seed_url="https://test.com"
            )

            # Update to running
            updated = await job_repo.update_status(
                str(job.id), status="running", started_at=datetime.now(UTC)
            )

            assert updated is not None
            assert updated.status.value == "running"
            assert updated.started_at is not None

    async def test_get_pending_jobs(self, db_session: AsyncSession) -> None:
        """Test getting pending jobs ordered by priority."""
        async with db_session.begin():
            conn = await db_session.connection()
            website_repo = WebsiteRepository(conn)
            job_repo = CrawlJobRepository(conn)

            website = await website_repo.create(
                name="pending-test-site", base_url="https://test.com", config={}
            )

            # Create jobs with different priorities
            await job_repo.create(
                website_id=str(website.id),
                seed_url="https://test.com/low",
                priority=3,
            )
            await job_repo.create(
                website_id=str(website.id),
                seed_url="https://test.com/high",
                priority=9,
            )

            pending = await job_repo.get_pending(limit=10)
            assert len(pending) >= 2

            # First job should have highest priority
            assert pending[0].priority >= pending[1].priority


@pytest.mark.asyncio
class TestCrawledPageRepository:
    """Tests for CrawledPageRepository."""

    async def test_create_and_get_page(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a crawled page."""
        async with db_session.begin():
            conn = await db_session.connection()
            website_repo = WebsiteRepository(conn)
            job_repo = CrawlJobRepository(conn)
            page_repo = CrawledPageRepository(conn)

            website = await website_repo.create(
                name="page-test-site", base_url="https://test.com", config={}
            )
            job = await job_repo.create(
                website_id=str(website.id), seed_url="https://test.com"
            )

            # Create page
            page = await page_repo.create(
                website_id=str(website.id),
                job_id=str(job.id),
                url="https://test.com/page1",
                url_hash="a" * 64,
                content_hash="b" * 64,
                title="Test Page",
                crawled_at=datetime.now(UTC),
            )

            assert page.url == "https://test.com/page1"
            assert page.title == "Test Page"
            assert page.is_duplicate is False

            # Get by URL hash
            fetched = await page_repo.get_by_url_hash(str(website.id), "a" * 64)
            assert fetched is not None
            assert fetched.url == "https://test.com/page1"


@pytest.mark.asyncio
class TestContentHashRepository:
    """Tests for ContentHashRepository."""

    async def test_upsert_content_hash(self, db_session: AsyncSession) -> None:
        """Test upserting content hashes."""
        async with db_session.begin():
            conn = await db_session.connection()
            website_repo = WebsiteRepository(conn)
            job_repo = CrawlJobRepository(conn)
            page_repo = CrawledPageRepository(conn)
            hash_repo = ContentHashRepository(conn)

            website = await website_repo.create(
                name="hash-test-site", base_url="https://test.com", config={}
            )
            job = await job_repo.create(
                website_id=str(website.id), seed_url="https://test.com"
            )
            page = await page_repo.create(
                website_id=str(website.id),
                job_id=str(job.id),
                url="https://test.com/page1",
                url_hash="c" * 64,
                content_hash="d" * 64,
                crawled_at=datetime.now(UTC),
            )

            # First upsert
            hash1 = await hash_repo.upsert("unique_hash_" + "e" * 52, str(page.id))
            assert hash1.occurrence_count == 1

            # Second upsert should increment
            hash2 = await hash_repo.upsert("unique_hash_" + "e" * 52, str(page.id))
            assert hash2.occurrence_count == 2


@pytest.mark.asyncio
class TestCrawlLogRepository:
    """Tests for CrawlLogRepository."""

    async def test_create_and_list_logs(self, db_session: AsyncSession) -> None:
        """Test creating and listing logs."""
        async with db_session.begin():
            conn = await db_session.connection()
            website_repo = WebsiteRepository(conn)
            job_repo = CrawlJobRepository(conn)
            log_repo = CrawlLogRepository(conn)

            website = await website_repo.create(
                name="log-test-site", base_url="https://test.com", config={}
            )
            job = await job_repo.create(
                website_id=str(website.id), seed_url="https://test.com"
            )

            # Create logs
            await log_repo.create(
                job_id=str(job.id),
                website_id=str(website.id),
                message="Test info log",
                log_level="INFO",
            )
            await log_repo.create(
                job_id=str(job.id),
                website_id=str(website.id),
                message="Test error log",
                log_level="ERROR",
            )

            # List all logs
            all_logs = await log_repo.list_by_job(str(job.id), limit=10)
            assert len(all_logs) == 2

            # Get only errors
            errors = await log_repo.get_errors(str(job.id), limit=10)
            assert len(errors) >= 1
            assert all(log.log_level.value in ["ERROR", "CRITICAL"] for log in errors)
