"""Integration tests for URL deduplication cache service.

These tests verify URL normalization, caching, TTL, and performance requirements
using a real Redis connection.
"""

import time
from datetime import UTC, datetime

import pytest
import redis.asyncio as redis

from config import Settings
from crawler.services.redis_cache import URLDeduplicationCache


@pytest.mark.asyncio
class TestURLDeduplicationCache:
    """Integration tests for URLDeduplicationCache service."""

    async def test_set_and_get_with_default_ttl(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test setting and getting URL with default TTL (24 hours)."""
        cache = URLDeduplicationCache(redis_client, settings)
        url_hash = "test_hash_default_ttl"
        data = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "crawled_at": datetime.now(UTC).isoformat(),
        }

        # Set without explicit TTL - should use url_dedup_ttl (24h = 86400s)
        result = await cache.set(url_hash, data)
        assert result is True

        # Verify data can be retrieved
        retrieved = await cache.get(url_hash)
        assert retrieved is not None
        assert retrieved["job_id"] == data["job_id"]
        assert retrieved["crawled_at"] == data["crawled_at"]

        # Verify TTL is set correctly (allow grace window for test execution time)
        ttl = await redis_client.ttl(f"url:dedup:{url_hash}")
        expected_ttl = settings.url_dedup_ttl
        assert ttl >= expected_ttl - 100  # Allow up to 100 seconds for test execution
        assert ttl <= expected_ttl

    async def test_set_with_custom_ttl(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test setting URL with custom TTL."""
        cache = URLDeduplicationCache(redis_client, settings)
        url_hash = "test_hash_custom_ttl"
        data = {"job_id": "test_job"}
        custom_ttl = 300  # 5 minutes

        result = await cache.set(url_hash, data, ttl=custom_ttl)
        assert result is True

        # Verify TTL is set correctly
        ttl = await redis_client.ttl(f"url:dedup:{url_hash}")
        assert ttl > 290  # At least 290 seconds
        assert ttl <= 300

    async def test_url_normalization_with_tracking_params(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test that URLs with tracking parameters normalize to same hash."""
        cache = URLDeduplicationCache(redis_client, settings)

        url_without_tracking = "https://example.com/page?page=2&category=tech"
        url_with_tracking = "https://example.com/page?utm_source=fb&page=2&category=tech&fbclid=123"

        data = {"job_id": "test_job"}

        # Set URL with tracking parameters
        await cache.set_url(url_with_tracking, data)

        # Retrieve using URL without tracking parameters
        retrieved = await cache.get_url(url_without_tracking)
        assert retrieved is not None
        assert retrieved["job_id"] == "test_job"

    async def test_url_normalization_case_insensitive_host(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test that URLs with different case hostnames normalize to same hash."""
        cache = URLDeduplicationCache(redis_client, settings)

        url_lowercase = "https://example.com/page"
        url_uppercase = "https://EXAMPLE.COM/page"
        url_mixed = "https://Example.Com/page"

        data = {"job_id": "test_job"}

        # Set URL with uppercase host
        await cache.set_url(url_uppercase, data)

        # All variations should retrieve the same data
        assert await cache.get_url(url_lowercase) is not None
        assert await cache.get_url(url_uppercase) is not None
        assert await cache.get_url(url_mixed) is not None

    async def test_url_normalization_parameter_order(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test that URLs with different parameter order normalize to same hash."""
        cache = URLDeduplicationCache(redis_client, settings)

        url1 = "https://example.com/page?z=3&a=1&b=2"
        url2 = "https://example.com/page?a=1&b=2&z=3"

        data = {"job_id": "test_job"}

        await cache.set_url(url1, data)

        # Should retrieve same data regardless of parameter order
        retrieved = await cache.get_url(url2)
        assert retrieved is not None
        assert retrieved["job_id"] == "test_job"

    async def test_url_normalization_fragment_removal(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test that URL fragments are removed during normalization."""
        cache = URLDeduplicationCache(redis_client, settings)

        url_with_fragment = "https://example.com/page#section1"
        url_without_fragment = "https://example.com/page"

        data = {"job_id": "test_job"}

        await cache.set_url(url_with_fragment, data)

        # Should retrieve same data with or without fragment
        assert await cache.get_url(url_without_fragment) is not None
        assert await cache.get_url(url_with_fragment) is not None

    async def test_exists_url(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test checking if normalized URL exists in cache."""
        cache = URLDeduplicationCache(redis_client, settings)

        url = "https://example.com/page?page=2"
        url_with_tracking = "https://example.com/page?utm_source=fb&page=2"

        # URL should not exist initially
        assert await cache.exists_url(url) is False

        # Set URL
        await cache.set_url(url, {"job_id": "test"})

        # Both normalized versions should exist
        assert await cache.exists_url(url) is True
        assert await cache.exists_url(url_with_tracking) is True

    async def test_delete_url(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test deleting normalized URL from cache."""
        cache = URLDeduplicationCache(redis_client, settings)

        url = "https://example.com/page"
        url_with_tracking = "https://example.com/page?utm_campaign=test"

        # Set URL
        await cache.set_url(url, {"job_id": "test"})
        assert await cache.exists_url(url) is True

        # Delete using URL with tracking params (should delete same entry)
        result = await cache.delete_url(url_with_tracking)
        assert result is True

        # Both should not exist anymore
        assert await cache.exists_url(url) is False
        assert await cache.exists_url(url_with_tracking) is False

    async def test_batch_exists_check(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test batch checking of multiple URL hashes."""
        cache = URLDeduplicationCache(redis_client, settings)

        # Create test URLs and hashes
        from crawler.utils import hash_url

        urls = [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
            "https://example.com/page4",
        ]
        hashes = [hash_url(url, normalize=True) for url in urls]

        # Store only first two URLs
        await cache.set_url(urls[0], {"job_id": "job1"})
        await cache.set_url(urls[1], {"job_id": "job2"})

        # Batch check all hashes
        existing = await cache.exists_batch(hashes)

        # Should only return first two hashes
        assert len(existing) == 2
        assert hashes[0] in existing
        assert hashes[1] in existing
        assert hashes[2] not in existing
        assert hashes[3] not in existing

    async def test_empty_batch_check(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test batch checking with empty list."""
        cache = URLDeduplicationCache(redis_client, settings)

        existing = await cache.exists_batch([])
        assert existing == set()

    async def test_metadata_storage(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test that metadata is correctly stored and retrieved."""
        cache = URLDeduplicationCache(redis_client, settings)

        url = "https://example.com/page"
        metadata = {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "crawled_at": "2024-01-15T10:30:00Z",
            "status_code": 200,
            "content_type": "text/html",
        }

        await cache.set_url(url, metadata)

        retrieved = await cache.get_url(url)
        assert retrieved is not None
        assert retrieved["job_id"] == metadata["job_id"]
        assert retrieved["crawled_at"] == metadata["crawled_at"]
        assert retrieved["status_code"] == metadata["status_code"]
        assert retrieved["content_type"] == metadata["content_type"]

    async def test_nonexistent_url_returns_none(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test that getting nonexistent URL returns None."""
        cache = URLDeduplicationCache(redis_client, settings)

        url = "https://example.com/nonexistent"
        result = await cache.get_url(url)
        assert result is None


@pytest.mark.asyncio
class TestURLDeduplicationPerformance:
    """Performance tests for URL deduplication cache."""

    async def test_exists_url_performance(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test that exists_url check completes in < 10ms."""
        cache = URLDeduplicationCache(redis_client, settings)

        url = "https://example.com/performance-test"
        await cache.set_url(url, {"job_id": "perf_test"})

        # Warm up Redis connection
        await cache.exists_url(url)

        # Measure performance over multiple iterations
        iterations = 100
        start = time.perf_counter()

        for _ in range(iterations):
            await cache.exists_url(url)

        elapsed = time.perf_counter() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Average should be well under 10ms (typically < 1ms for local Redis)
        assert avg_time_ms < 10, f"Average time {avg_time_ms:.2f}ms exceeds 10ms limit"

    async def test_get_url_performance(self, redis_client: redis.Redis, settings: Settings) -> None:
        """Test that get_url check completes in < 10ms."""
        cache = URLDeduplicationCache(redis_client, settings)

        url = "https://example.com/performance-test-get"
        metadata = {
            "job_id": "perf_test",
            "crawled_at": datetime.now(UTC).isoformat(),
            "status_code": 200,
        }
        await cache.set_url(url, metadata)

        # Warm up
        await cache.get_url(url)

        # Measure performance
        iterations = 100
        start = time.perf_counter()

        for _ in range(iterations):
            await cache.get_url(url)

        elapsed = time.perf_counter() - start
        avg_time_ms = (elapsed / iterations) * 1000

        assert avg_time_ms < 10, f"Average time {avg_time_ms:.2f}ms exceeds 10ms limit"

    async def test_batch_check_performance(
        self, redis_client: redis.Redis, settings: Settings
    ) -> None:
        """Test that batch exists check is performant for multiple URLs."""
        cache = URLDeduplicationCache(redis_client, settings)
        from crawler.utils import hash_url

        # Create 100 test URLs
        urls = [f"https://example.com/page{i}" for i in range(100)]
        hashes = [hash_url(url, normalize=True) for url in urls]

        # Store half of them
        for url in urls[:50]:
            await cache.set_url(url, {"job_id": f"job_{url}"})

        # Warm up
        await cache.exists_batch(hashes)

        # Measure batch check performance
        iterations = 10
        start = time.perf_counter()

        for _ in range(iterations):
            await cache.exists_batch(hashes)

        elapsed = time.perf_counter() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Batch check of 100 URLs should complete in < 50ms (generous limit)
        assert avg_time_ms < 50, f"Average batch time {avg_time_ms:.2f}ms exceeds 50ms limit"
