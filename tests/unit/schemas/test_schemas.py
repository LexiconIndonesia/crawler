"""Unit tests for Pydantic schemas."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from crawler.schemas import (
    ContentHashCreate,
    CrawledPageCreate,
    CrawlJobCancel,
    CrawlJobCreate,
    CrawlJobUpdate,
    CrawlLogCreate,
    WebsiteCreate,
    WebsiteUpdate,
)


class TestWebsiteSchemas:
    """Tests for Website schemas."""

    def test_website_create_valid(self) -> None:
        """Test valid website creation."""
        data = {
            "name": "test-site",
            "base_url": "https://example.com",
            "config": {"max_depth": 3},
            "created_by": "admin@example.com",
        }
        website = WebsiteCreate(**data)  # type: ignore[arg-type]
        assert website.name == "test-site"
        assert str(website.base_url) == "https://example.com/"
        assert website.config == {"max_depth": 3}

    def test_website_create_minimal(self) -> None:
        """Test website creation with minimal fields."""
        data = {"name": "test-site", "base_url": "https://example.com"}
        website = WebsiteCreate(**data)  # type: ignore[arg-type]
        assert website.name == "test-site"
        assert website.config == {}
        assert website.status == "active"

    def test_website_create_invalid_url(self) -> None:
        """Test website creation with invalid URL."""
        data = {"name": "test-site", "base_url": "not-a-url"}
        with pytest.raises(ValidationError):
            WebsiteCreate(**data)  # type: ignore[arg-type]

    def test_website_update_partial(self) -> None:
        """Test partial website update."""
        data = {"status": "inactive"}
        update = WebsiteUpdate(**data)  # type: ignore[arg-type]
        assert update.status == "inactive"
        assert update.name is None

    def test_website_create_with_cron_schedule(self) -> None:
        """Test website creation with cron schedule."""
        data = {
            "name": "scheduled-site",
            "base_url": "https://example.com",
            "cron_schedule": "0 0 1,15 * *",
        }
        website = WebsiteCreate(**data)  # type: ignore[arg-type]
        assert website.cron_schedule == "0 0 1,15 * *"

    def test_website_create_without_cron_schedule(self) -> None:
        """Test website creation without cron schedule."""
        data = {"name": "test-site", "base_url": "https://example.com"}
        website = WebsiteCreate(**data)  # type: ignore[arg-type]
        assert website.cron_schedule is None

    def test_website_update_cron_schedule(self) -> None:
        """Test updating website cron schedule."""
        data = {"cron_schedule": "0 12 * * *"}
        update = WebsiteUpdate(**data)  # type: ignore[arg-type]
        assert update.cron_schedule == "0 12 * * *"


class TestCrawlJobSchemas:
    """Tests for CrawlJob schemas."""

    def test_crawl_job_create_valid(self) -> None:
        """Test valid crawl job creation."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "seed_url": "https://example.com",
            "job_type": "one_time",
            "priority": 7,
        }
        job = CrawlJobCreate(**data)  # type: ignore[arg-type]
        assert job.website_id == "123e4567-e89b-12d3-a456-426614174000"
        assert job.priority == 7
        assert job.status == "pending"

    def test_crawl_job_invalid_priority(self) -> None:
        """Test crawl job with invalid priority."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "seed_url": "https://example.com",
            "priority": 11,  # Invalid: > 10
        }
        with pytest.raises(ValidationError):
            CrawlJobCreate(**data)  # type: ignore[arg-type]

    def test_crawl_job_invalid_job_type(self) -> None:
        """Test crawl job with invalid job type."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "seed_url": "https://example.com",
            "job_type": "invalid_type",
        }
        with pytest.raises(ValidationError):
            CrawlJobCreate(**data)  # type: ignore[arg-type]

    def test_crawl_job_invalid_status(self) -> None:
        """Test crawl job with invalid status."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "seed_url": "https://example.com",
            "status": "invalid_status",
        }
        with pytest.raises(ValidationError):
            CrawlJobCreate(**data)  # type: ignore[arg-type]

    def test_crawl_job_update_partial(self) -> None:
        """Test partial job update."""
        data = {"status": "running", "error_message": None}
        update = CrawlJobUpdate(**data)  # type: ignore[arg-type]
        assert update.status == "running"

    def test_crawl_job_cancel(self) -> None:
        """Test job cancellation schema."""
        data = {"cancelled_by": "admin@example.com", "cancellation_reason": "Test cancellation"}
        cancel = CrawlJobCancel(**data)
        assert cancel.cancelled_by == "admin@example.com"
        assert cancel.cancellation_reason == "Test cancellation"


class TestCrawledPageSchemas:
    """Tests for CrawledPage schemas."""

    def test_crawled_page_create_valid(self) -> None:
        """Test valid crawled page creation."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "job_id": "987fcdeb-51a2-43f1-b4e5-123456789abc",
            "url": "https://example.com/page1",
            "url_hash": "a" * 64,
            "content_hash": "b" * 64,
            "title": "Example Page",
            "crawled_at": datetime.now(UTC),
        }
        page = CrawledPageCreate(**data)  # type: ignore[arg-type]
        assert page.url_hash == "a" * 64
        assert page.is_duplicate is False

    def test_crawled_page_invalid_similarity(self) -> None:
        """Test crawled page with invalid similarity score."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "job_id": "987fcdeb-51a2-43f1-b4e5-123456789abc",
            "url": "https://example.com/page1",
            "url_hash": "a" * 64,
            "content_hash": "b" * 64,
            "crawled_at": datetime.now(UTC),
            "similarity_score": 101,  # Invalid: > 100
        }
        with pytest.raises(ValidationError):
            CrawledPageCreate(**data)  # type: ignore[arg-type]


class TestContentHashSchemas:
    """Tests for ContentHash schemas."""

    def test_content_hash_create_valid(self) -> None:
        """Test valid content hash creation."""
        data = {
            "content_hash": "a" * 64,
            "first_seen_page_id": "123e4567-e89b-12d3-a456-426614174000",
            "occurrence_count": 1,
            "last_seen_at": datetime.now(UTC),
        }
        hash_obj = ContentHashCreate(**data)  # type: ignore[arg-type]
        assert hash_obj.content_hash == "a" * 64
        assert hash_obj.occurrence_count == 1


class TestCrawlLogSchemas:
    """Tests for CrawlLog schemas."""

    def test_crawl_log_create_valid(self) -> None:
        """Test valid crawl log creation."""
        data = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "website_id": "987fcdeb-51a2-43f1-b4e5-123456789abc",
            "message": "Test log message",
            "log_level": "INFO",
            "context": {"url": "https://example.com"},
        }
        log = CrawlLogCreate(**data)  # type: ignore[arg-type]
        assert log.message == "Test log message"
        assert log.log_level == "INFO"

    def test_crawl_log_level_uppercase(self) -> None:
        """Test log level is converted to uppercase."""
        data = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "website_id": "987fcdeb-51a2-43f1-b4e5-123456789abc",
            "message": "Test",
            "log_level": "info",  # lowercase
        }
        log = CrawlLogCreate(**data)  # type: ignore[arg-type]
        assert log.log_level == "INFO"  # Should be uppercase

    def test_crawl_log_invalid_level(self) -> None:
        """Test crawl log with invalid log level."""
        data = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "website_id": "987fcdeb-51a2-43f1-b4e5-123456789abc",
            "message": "Test",
            "log_level": "INVALID",
        }
        with pytest.raises(ValidationError):
            CrawlLogCreate(**data)  # type: ignore[arg-type]
