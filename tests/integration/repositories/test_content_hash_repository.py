"""Integration tests for ContentHashRepository.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.repositories import (
    ContentHashRepository,
    CrawledPageRepository,
    CrawlJobRepository,
    WebsiteRepository,
)


@pytest.mark.asyncio
class TestContentHashRepository:
    """Tests for ContentHashRepository."""

    async def test_upsert_content_hash(self, db_session: AsyncSession) -> None:
        """Test upserting content hashes."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)
        page_repo = CrawledPageRepository(conn)
        hash_repo = ContentHashRepository(conn)

        website = await website_repo.create(
            name="hash-test-site", base_url="https://test.com", config={}
        )
        job = await job_repo.create(seed_url="https://test.com", website_id=str(website.id))
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
