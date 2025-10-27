"""Integration tests for database operations using sqlc repositories.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

from datetime import UTC, datetime

import pytest

from crawler.db.repositories import (
    ContentHashRepository,
    CrawlJobRepository,
    CrawledPageRepository,
    WebsiteRepository,
)


@pytest.mark.asyncio
class TestWebsiteRepository:
    """Tests for website repository operations."""

    async def test_create_website(self, website_repo: WebsiteRepository) -> None:
        """Test creating a website."""
        result = await website_repo.create(
            name="test-site",
            base_url="https://example.com",
            config={"max_depth": 3},
            created_by="test@example.com",
        )
        assert result is not None
        assert result.name == "test-site"
        assert result.base_url == "https://example.com"
        assert result.config == {"max_depth": 3}

    async def test_get_website_by_id(self, website_repo: WebsiteRepository) -> None:
        """Test getting website by ID."""
        created = await website_repo.create(
            name="test-site-2", base_url="https://example2.com", config={}
        )
        assert created is not None

        result = await website_repo.get_by_id(created.id)
        assert result is not None
        assert result.id == created.id
        assert result.name == "test-site-2"

    async def test_get_website_by_name(self, website_repo: WebsiteRepository) -> None:
        """Test getting website by name."""
        await website_repo.create(
            name="test-site-3", base_url="https://example3.com", config={}
        )

        result = await website_repo.get_by_name("test-site-3")
        assert result is not None
        assert result.name == "test-site-3"

    async def test_update_website(self, website_repo: WebsiteRepository) -> None:
        """Test updating website."""
        created = await website_repo.create(
            name="test-site-4", base_url="https://example4.com", config={}
        )
        assert created is not None

        result = await website_repo.update(created.id, status="inactive")
        assert result is not None
        assert result.status == "inactive"
        # Note: updated_at might equal created_at depending on database precision
        assert result.updated_at >= result.created_at

    async def test_list_websites(self, website_repo: WebsiteRepository) -> None:
        """Test listing websites."""
        await website_repo.create(name="list-test-1", base_url="https://test1.com", config={})
        await website_repo.create(name="list-test-2", base_url="https://test2.com", config={})

        results = await website_repo.list(limit=10)
        assert len(results) >= 2

    async def test_count_websites(self, website_repo: WebsiteRepository) -> None:
        """Test counting websites."""
        await website_repo.create(name="count-test-1", base_url="https://test1.com", config={})
        await website_repo.create(
            name="count-test-2", base_url="https://test2.com", config={}, status="active"
        )

        count = await website_repo.count()
        assert count >= 2

    async def test_delete_website(self, website_repo: WebsiteRepository) -> None:
        """Test deleting website."""
        created = await website_repo.create(
            name="delete-test", base_url="https://delete.com", config={}
        )
        assert created is not None

        await website_repo.delete(created.id)

        result = await website_repo.get_by_id(created.id)
        assert result is None


@pytest.mark.asyncio
class TestCrawlJobRepository:
    """Tests for crawl job repository operations."""

    async def test_create_crawl_job(
        self, website_repo: WebsiteRepository, crawl_job_repo: CrawlJobRepository
    ) -> None:
        """Test creating a crawl job."""
        site = await website_repo.create(
            name="job-test-site", base_url="https://test.com", config={}
        )
        assert site is not None

        result = await crawl_job_repo.create(
            website_id=site.id,
            seed_url="https://test.com/page1",
            job_type="one_time",
            priority=7,
        )
        assert result is not None
        assert result.website_id == site.id
        assert result.seed_url == "https://test.com/page1"
        assert result.priority == 7
        assert result.status == "pending"

    async def test_get_crawl_job_by_id(
        self, website_repo: WebsiteRepository, crawl_job_repo: CrawlJobRepository
    ) -> None:
        """Test getting crawl job by ID."""
        site = await website_repo.create(
            name="job-test-site-2", base_url="https://test.com", config={}
        )
        assert site is not None

        created = await crawl_job_repo.create(
            website_id=site.id, seed_url="https://test.com/page2"
        )
        assert created is not None

        result = await crawl_job_repo.get_by_id(created.id)
        assert result is not None
        assert result.id == created.id

    async def test_update_job_status(
        self, website_repo: WebsiteRepository, crawl_job_repo: CrawlJobRepository
    ) -> None:
        """Test updating crawl job status."""
        site = await website_repo.create(
            name="job-test-site-3", base_url="https://test.com", config={}
        )
        assert site is not None

        created = await crawl_job_repo.create(
            website_id=site.id, seed_url="https://test.com/page3"
        )
        assert created is not None

        result = await crawl_job_repo.update_status(created.id, status="running")
        assert result is not None
        assert result.status == "running"
        assert result.started_at is not None

    async def test_update_job_progress(
        self, website_repo: WebsiteRepository, crawl_job_repo: CrawlJobRepository
    ) -> None:
        """Test updating crawl job progress."""
        site = await website_repo.create(
            name="job-test-site-4", base_url="https://test.com", config={}
        )
        assert site is not None

        created = await crawl_job_repo.create(
            website_id=site.id, seed_url="https://test.com/page4"
        )
        assert created is not None

        result = await crawl_job_repo.update_progress(
            created.id, progress={"pages_crawled": 10, "pages_pending": 5}
        )
        assert result is not None
        assert result.progress == {"pages_crawled": 10, "pages_pending": 5}

    async def test_get_pending_jobs(
        self, website_repo: WebsiteRepository, crawl_job_repo: CrawlJobRepository
    ) -> None:
        """Test getting pending jobs."""
        site = await website_repo.create(
            name="pending-test-site", base_url="https://test.com", config={}
        )
        assert site is not None

        await crawl_job_repo.create(
            website_id=site.id, seed_url="https://test.com/pending", priority=10
        )

        results = await crawl_job_repo.get_pending(limit=10)
        assert len(results) >= 1

    async def test_cancel_job(
        self, website_repo: WebsiteRepository, crawl_job_repo: CrawlJobRepository
    ) -> None:
        """Test cancelling a job."""
        site = await website_repo.create(
            name="cancel-test-site", base_url="https://test.com", config={}
        )
        assert site is not None

        created = await crawl_job_repo.create(
            website_id=site.id, seed_url="https://test.com/cancel"
        )
        assert created is not None

        result = await crawl_job_repo.cancel(
            created.id, cancelled_by="test@example.com", reason="Testing"
        )
        assert result is not None
        assert result.status == "cancelled"
        assert result.cancelled_by == "test@example.com"


@pytest.mark.asyncio
class TestCrawledPageRepository:
    """Tests for crawled page repository operations."""

    async def test_create_crawled_page(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
    ) -> None:
        """Test creating a crawled page."""
        site = await website_repo.create(
            name="page-test-site", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        result = await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/page1",
            url_hash="hash123",
            content_hash="content123",
            title="Test Page",
            extracted_content="Test content",
            metadata={"key": "value"},
            gcs_html_path="gs://bucket/page1.html",
            crawled_at=datetime.now(UTC),
        )
        assert result is not None
        assert result.url == "https://test.com/page1"
        assert result.title == "Test Page"

    async def test_get_page_by_id(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
    ) -> None:
        """Test getting page by ID."""
        site = await website_repo.create(
            name="page-test-site-2", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        created = await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/page2",
            url_hash="hash456",
            content_hash="content456",
            crawled_at=datetime.now(UTC),
        )
        assert created is not None

        result = await crawled_page_repo.get_by_id(created.id)
        assert result is not None
        assert result.id == created.id

    async def test_get_page_by_url_hash(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
    ) -> None:
        """Test getting page by URL hash."""
        site = await website_repo.create(
            name="page-test-site-3", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/page3",
            url_hash="unique_hash_789",
            content_hash="content789",
            crawled_at=datetime.now(UTC),
        )

        result = await crawled_page_repo.get_by_url_hash(site.id, "unique_hash_789")
        assert result is not None
        assert result.url_hash == "unique_hash_789"

    async def test_list_pages_by_job(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
    ) -> None:
        """Test listing pages by job."""
        site = await website_repo.create(
            name="page-list-site", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        for i in range(3):
            await crawled_page_repo.create(
                website_id=site.id,
                job_id=job.id,
                url=f"https://test.com/page{i}",
                url_hash=f"hash{i}",
                content_hash=f"content{i}",
                crawled_at=datetime.now(UTC),
            )

        results = await crawled_page_repo.list_by_job(job.id, limit=10)
        assert len(results) == 3

    async def test_mark_as_duplicate(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
    ) -> None:
        """Test marking page as duplicate."""
        site = await website_repo.create(
            name="dup-test-site", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        original = await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/original",
            url_hash="hash_original",
            content_hash="content_same",
            crawled_at=datetime.now(UTC),
        )
        assert original is not None

        duplicate = await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/duplicate",
            url_hash="hash_dup",
            content_hash="content_same",
            crawled_at=datetime.now(UTC),
        )
        assert duplicate is not None

        result = await crawled_page_repo.mark_as_duplicate(
            duplicate.id, duplicate_of=original.id, similarity_score=95
        )
        assert result is not None
        assert result.duplicate_of == original.id
        assert result.similarity_score == 95


@pytest.mark.asyncio
class TestContentHashRepository:
    """Tests for content hash repository operations."""

    async def test_upsert_content_hash_new(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
        content_hash_repo: ContentHashRepository,
    ) -> None:
        """Test upserting a new content hash."""
        site = await website_repo.create(
            name="hash-test-site", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        page = await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/hash1",
            url_hash="url_hash_1",
            content_hash="unique_content_1",
            crawled_at=datetime.now(UTC),
        )
        assert page is not None

        result = await content_hash_repo.upsert("unique_content_1", page.id)
        assert result is not None
        assert result.content_hash == "unique_content_1"
        assert result.first_seen_page_id == page.id
        assert result.occurrence_count == 1

    async def test_upsert_content_hash_increment(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
        content_hash_repo: ContentHashRepository,
    ) -> None:
        """Test upserting existing content hash increments count."""
        site = await website_repo.create(
            name="hash-inc-site", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        page = await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/hash2",
            url_hash="url_hash_2",
            content_hash="common_content",
            crawled_at=datetime.now(UTC),
        )
        assert page is not None

        first = await content_hash_repo.upsert("common_content", page.id)
        assert first is not None
        assert first.occurrence_count == 1

        # Upsert again
        second = await content_hash_repo.upsert("common_content", page.id)
        assert second is not None
        assert second.occurrence_count == 2

    async def test_get_content_hash(
        self,
        website_repo: WebsiteRepository,
        crawl_job_repo: CrawlJobRepository,
        crawled_page_repo: CrawledPageRepository,
        content_hash_repo: ContentHashRepository,
    ) -> None:
        """Test getting content hash record."""
        site = await website_repo.create(
            name="hash-get-site", base_url="https://test.com", config={}
        )
        assert site is not None

        job = await crawl_job_repo.create(website_id=site.id, seed_url="https://test.com")
        assert job is not None

        page = await crawled_page_repo.create(
            website_id=site.id,
            job_id=job.id,
            url="https://test.com/hash3",
            url_hash="url_hash_3",
            content_hash="get_test_content",
            crawled_at=datetime.now(UTC),
        )
        assert page is not None

        await content_hash_repo.upsert("get_test_content", page.id)

        result = await content_hash_repo.get("get_test_content")
        assert result is not None
        assert result.content_hash == "get_test_content"
