"""Integration tests for Redis cache services.

These tests require a running Redis instance.
Run with: make test-integration
"""

from datetime import UTC, datetime

import pytest
import redis.asyncio as redis

from config import Settings
from crawler.services import (
    BrowserPoolStatus,
    JobCancellationFlag,
    JobProgressCache,
    RateLimiter,
    URLDeduplicationCache,
)


@pytest.mark.asyncio
class TestURLDeduplicationCache:
    """Tests for URL deduplication cache."""

    async def test_set_and_get(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test setting and getting URL hash."""
        cache = URLDeduplicationCache(redis_client, settings)
        url_hash = "test_hash_123"
        data = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "crawled_at": datetime.now(UTC).isoformat(),
        }

        result = await cache.set(url_hash, data, ttl=60)
        assert result is True

        retrieved = await cache.get(url_hash)
        assert retrieved is not None
        assert retrieved["job_id"] == data["job_id"]

    async def test_exists(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test checking if URL hash exists."""
        cache = URLDeduplicationCache(redis_client, settings)
        url_hash = "test_hash_456"
        data = {"job_id": "test"}

        exists_before = await cache.exists(url_hash)
        assert exists_before is False

        await cache.set(url_hash, data, ttl=60)

        exists_after = await cache.exists(url_hash)
        assert exists_after is True

    async def test_delete(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test deleting URL hash."""
        cache = URLDeduplicationCache(redis_client, settings)
        url_hash = "test_hash_789"
        data = {"job_id": "test"}

        await cache.set(url_hash, data, ttl=60)
        assert await cache.exists(url_hash) is True

        result = await cache.delete(url_hash)
        assert result is True
        assert await cache.exists(url_hash) is False

    async def test_url_deduplication_workflow(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test complete URL deduplication workflow with real URLs."""
        cache = URLDeduplicationCache(redis_client, settings)

        # Scenario: Crawler encounters same page with different tracking params
        original_url = "https://example.com/article/123?page=1"
        url_from_facebook = "https://example.com/article/123?page=1&utm_source=facebook&fbclid=xyz"
        url_from_google = "https://example.com/article/123?page=1&utm_source=google&gclid=abc"

        # First crawl - store original URL
        first_crawl_data = {
            "job_id": "job_1",
            "crawled_at": datetime.now(UTC).isoformat(),
            "status_code": 200,
        }
        await cache.set_url(original_url, first_crawl_data)

        # Second encounter - check if URL from Facebook was already crawled
        exists = await cache.exists_url(url_from_facebook)
        assert exists is True, "URL with Facebook tracking should be recognized as duplicate"

        # Retrieve metadata
        metadata = await cache.get_url(url_from_facebook)
        assert metadata is not None
        assert metadata["job_id"] == "job_1"
        assert metadata["status_code"] == 200

        # Third encounter - check if URL from Google was already crawled
        exists = await cache.exists_url(url_from_google)
        assert exists is True, "URL with Google tracking should be recognized as duplicate"

    async def test_batch_deduplication_check(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test batch checking for deduplication across multiple URLs."""
        cache = URLDeduplicationCache(redis_client, settings)
        from crawler.utils import hash_url

        # Crawled URLs (stored in cache)
        crawled_urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]

        # New URLs to check (mix of duplicates and new)
        urls_to_check = [
            "https://example.com/page1?utm_source=fb",  # Duplicate
            "https://example.com/page2",  # Duplicate
            "https://example.com/page4",  # New
            "https://example.com/page5",  # New
        ]

        # Store crawled URLs
        for url in crawled_urls:
            await cache.set_url(url, {"job_id": "initial_crawl"})

        # Generate hashes for URLs to check
        hashes_to_check = [hash_url(url, normalize=True) for url in urls_to_check]

        # Batch check
        existing_hashes = await cache.exists_batch(hashes_to_check)

        # Should find 2 duplicates (page1 and page2)
        assert len(existing_hashes) == 2

        # Verify which ones are duplicates
        expected_duplicates = {
            hash_url("https://example.com/page1", normalize=True),
            hash_url("https://example.com/page2", normalize=True),
        }
        assert existing_hashes == expected_duplicates


@pytest.mark.asyncio
class TestJobCancellationFlag:
    """Tests for job cancellation flags."""

    async def test_set_and_check_cancellation(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test setting and checking cancellation flag."""
        flag = JobCancellationFlag(redis_client, settings)
        job_id = "test_job_123"

        # Clean up any previous state
        await flag.clear_cancellation(job_id)

        is_cancelled_before = await flag.is_cancelled(job_id)
        assert is_cancelled_before is False

        result = await flag.set_cancellation(job_id, reason="Test cancellation")
        assert result is True

        is_cancelled_after = await flag.is_cancelled(job_id)
        assert is_cancelled_after is True

    async def test_clear_cancellation(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test clearing cancellation flag."""
        flag = JobCancellationFlag(redis_client, settings)
        job_id = "test_job_456"

        # Clean up any previous state
        await flag.clear_cancellation(job_id)

        await flag.set_cancellation(job_id)
        assert await flag.is_cancelled(job_id) is True

        result = await flag.clear_cancellation(job_id)
        assert result is True
        assert await flag.is_cancelled(job_id) is False


@pytest.mark.asyncio
class TestRateLimiter:
    """Tests for rate limiter."""

    async def test_increment(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test incrementing request counter."""
        limiter = RateLimiter(redis_client, settings)
        website_id = "test_website_123"

        # Reset counter first
        await limiter.reset(website_id)

        count1 = await limiter.increment(website_id)
        assert count1 == 1

        count2 = await limiter.increment(website_id)
        assert count2 == 2

        count3 = await limiter.increment(website_id)
        assert count3 == 3

    async def test_get_count(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test getting current request count."""
        limiter = RateLimiter(redis_client, settings)
        website_id = "test_website_456"
        await limiter.reset(website_id)

        count_before = await limiter.get_count(website_id)
        assert count_before == 0

        await limiter.increment(website_id)
        await limiter.increment(website_id)

        count_after = await limiter.get_count(website_id)
        assert count_after == 2

    async def test_is_rate_limited(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test checking if rate limited."""
        limiter = RateLimiter(redis_client, settings)
        website_id = "test_website_789"
        await limiter.reset(website_id)

        is_limited_before = await limiter.is_rate_limited(website_id)
        assert is_limited_before is False

        # Increment many times (settings.rate_limit_requests is typically 1000)
        # We'll just check the logic works
        for _ in range(5):
            await limiter.increment(website_id)

        is_limited_after = await limiter.is_rate_limited(website_id)
        # Should not be limited yet (limit is 1000 by default)
        assert is_limited_after is False

    async def test_reset(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test resetting rate limit counter."""
        limiter = RateLimiter(redis_client, settings)
        website_id = "test_website_reset"
        await limiter.reset(website_id)

        await limiter.increment(website_id)
        await limiter.increment(website_id)
        assert await limiter.get_count(website_id) == 2

        result = await limiter.reset(website_id)
        assert result is True
        assert await limiter.get_count(website_id) == 0


@pytest.mark.asyncio
class TestBrowserPoolStatus:
    """Tests for browser pool status tracker."""

    async def test_update_and_get_status(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test updating and getting browser pool status."""
        pool = BrowserPoolStatus(redis_client, settings)
        result = await pool.update_status(
            active_browsers=3, active_contexts=5, available_contexts=10, memory_mb=512.5
        )
        assert result is True

        status = await pool.get_status()
        assert status is not None
        assert status["active_browsers"] == 3
        assert status["active_contexts"] == 5
        assert status["available_contexts"] == 10
        assert status["memory_mb"] == 512.5


@pytest.mark.asyncio
class TestJobProgressCache:
    """Tests for job progress cache."""

    async def test_set_and_get_progress(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test setting and getting job progress."""
        cache = JobProgressCache(redis_client, settings)
        job_id = "test_job_progress_123"
        progress = {
            "pages_crawled": 150,
            "pages_pending": 50,
            "errors": 2,
            "last_update": datetime.now(UTC).isoformat(),
        }

        result = await cache.set_progress(job_id, progress)
        assert result is True

        retrieved = await cache.get_progress(job_id)
        assert retrieved is not None
        assert retrieved["pages_crawled"] == 150
        assert retrieved["pages_pending"] == 50

    async def test_delete_progress(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test deleting job progress."""
        cache = JobProgressCache(redis_client, settings)
        job_id = "test_job_progress_456"
        progress = {"pages_crawled": 100}

        await cache.set_progress(job_id, progress)
        assert await cache.get_progress(job_id) is not None

        result = await cache.delete_progress(job_id)
        assert result is True
        assert await cache.get_progress(job_id) is None
