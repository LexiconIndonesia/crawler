"""Integration tests for CrawledPageRepository.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.repositories import CrawledPageRepository, CrawlJobRepository, WebsiteRepository


@pytest.mark.asyncio
class TestCrawledPageRepository:
    """Tests for CrawledPageRepository."""

    async def test_create_and_get_page(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a crawled page."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)
        page_repo = CrawledPageRepository(conn)

        website = await website_repo.create(
            name="page-test-site", base_url="https://test.com", config={}
        )
        job = await job_repo.create(seed_url="https://test.com", website_id=str(website.id))

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
