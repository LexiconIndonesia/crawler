"""Unit tests for local rate limiter."""

import asyncio
import time

import pytest

from crawler.services.local_rate_limiter import LocalRateLimiter


class TestLocalRateLimiter:
    """Tests for LocalRateLimiter class."""

    def test_initialization_with_defaults(self) -> None:
        """Test rate limiter initialization with default values."""
        limiter = LocalRateLimiter()

        assert limiter.requests_per_second == 2.0
        assert limiter.concurrent_pages == 5
        assert limiter.burst == 10

    def test_initialization_with_custom_values(self) -> None:
        """Test rate limiter initialization with custom values."""
        limiter = LocalRateLimiter(requests_per_second=5.0, concurrent_pages=10, burst=20)

        assert limiter.requests_per_second == 5.0
        assert limiter.concurrent_pages == 10
        assert limiter.burst == 20

    def test_initialization_clamps_to_valid_ranges(self) -> None:
        """Test that initialization clamps values to valid ranges."""
        # Test lower bounds
        limiter_low = LocalRateLimiter(
            requests_per_second=0.01,  # Below min (0.1)
            concurrent_pages=0,  # Below min (1)
            burst=0,  # Below min (1)
        )
        assert limiter_low.requests_per_second == 0.1
        assert limiter_low.concurrent_pages == 1
        assert limiter_low.burst == 1

        # Test upper bounds
        limiter_high = LocalRateLimiter(
            requests_per_second=200.0,  # Above max (100)
            concurrent_pages=100,  # Above max (50)
            burst=200,  # Above max (100)
        )
        assert limiter_high.requests_per_second == 100.0
        assert limiter_high.concurrent_pages == 50
        assert limiter_high.burst == 100

    async def test_acquire_limits_concurrency(self) -> None:
        """Test that acquire() limits concurrent requests."""
        limiter = LocalRateLimiter(requests_per_second=100.0, concurrent_pages=2, burst=100)

        acquired_count = 0
        max_concurrent = 0

        async def request_with_tracking() -> None:
            nonlocal acquired_count, max_concurrent
            async with limiter.acquire():
                acquired_count += 1
                max_concurrent = max(max_concurrent, acquired_count)
                await asyncio.sleep(0.01)  # Simulate work
                acquired_count -= 1

        # Launch 5 concurrent requests
        tasks = [request_with_tracking() for _ in range(5)]
        await asyncio.gather(*tasks)

        # Max concurrent should not exceed concurrent_pages limit (2)
        assert max_concurrent == 2

    async def test_acquire_enforces_rate_limit(self) -> None:
        """Test that acquire() enforces requests per second limit."""
        # Set very low rate: 2 requests/second
        limiter = LocalRateLimiter(requests_per_second=2.0, concurrent_pages=10, burst=2)

        start_time = time.monotonic()
        request_times = []

        async def make_request() -> None:
            async with limiter.acquire():
                request_times.append(time.monotonic() - start_time)

        # Make 4 requests
        await asyncio.gather(*[make_request() for _ in range(4)])

        # First 2 requests should be immediate (burst allows it)
        assert request_times[0] < 0.1
        assert request_times[1] < 0.1

        # 3rd and 4th requests should be delayed (rate limiting kicks in)
        # At 2 req/s, each request takes 0.5s
        # 3rd request should wait ~0.5s, 4th should wait ~1.0s
        assert request_times[2] >= 0.3  # Allow some tolerance
        assert request_times[3] >= 0.5

    async def test_token_bucket_refills_over_time(self) -> None:
        """Test that token bucket refills tokens over time."""
        limiter = LocalRateLimiter(requests_per_second=10.0, concurrent_pages=10, burst=5)

        # Consume all burst tokens
        async def consume_burst() -> None:
            async with limiter.acquire():
                pass

        await asyncio.gather(*[consume_burst() for _ in range(5)])

        # Wait for tokens to refill (0.2s should give us ~2 tokens at 10 req/s)
        await asyncio.sleep(0.2)

        # Should be able to make 2 more requests without significant delay
        start = time.monotonic()
        await asyncio.gather(*[consume_burst() for _ in range(2)])
        elapsed = time.monotonic() - start

        # Should complete quickly since tokens refilled
        assert elapsed < 0.1

    async def test_from_config_with_valid_config(self) -> None:
        """Test from_config() with valid configuration."""
        config = {
            "requests_per_second": 3.0,
            "concurrent_pages": 7,
            "burst": 15,
        }

        limiter = LocalRateLimiter.from_config(config)

        assert limiter.requests_per_second == 3.0
        assert limiter.concurrent_pages == 7
        assert limiter.burst == 15

    async def test_from_config_with_none(self) -> None:
        """Test from_config() with None returns default limiter."""
        limiter = LocalRateLimiter.from_config(None)

        assert limiter.requests_per_second == 2.0
        assert limiter.concurrent_pages == 5
        assert limiter.burst == 10

    async def test_from_config_with_empty_dict(self) -> None:
        """Test from_config() with empty dict returns default limiter."""
        limiter = LocalRateLimiter.from_config({})

        assert limiter.requests_per_second == 2.0
        assert limiter.concurrent_pages == 5
        assert limiter.burst == 10

    async def test_from_config_with_partial_config(self) -> None:
        """Test from_config() with partial config uses defaults for missing values."""
        config = {"requests_per_second": 7.0}  # Only one field

        limiter = LocalRateLimiter.from_config(config)

        assert limiter.requests_per_second == 7.0
        assert limiter.concurrent_pages == 5  # Default
        assert limiter.burst == 10  # Default

    async def test_acquire_releases_on_exception(self) -> None:
        """Test that acquire() releases semaphore even if user code raises exception."""
        limiter = LocalRateLimiter(requests_per_second=100.0, concurrent_pages=1, burst=100)

        # First acquire should work
        with pytest.raises(RuntimeError, match="Test exception"):
            async with limiter.acquire():
                raise RuntimeError("Test exception")

        # Semaphore should be released - second acquire should work
        acquired = False
        async with limiter.acquire():
            acquired = True

        assert acquired is True

    async def test_concurrent_acquires_wait_for_semaphore(self) -> None:
        """Test that concurrent acquires wait for semaphore availability."""
        limiter = LocalRateLimiter(requests_per_second=100.0, concurrent_pages=1, burst=100)

        execution_order = []

        async def task(task_id: int) -> None:
            async with limiter.acquire():
                execution_order.append(f"start_{task_id}")
                await asyncio.sleep(0.01)
                execution_order.append(f"end_{task_id}")

        # Launch 3 tasks concurrently
        await asyncio.gather(*[task(i) for i in range(3)])

        # Should execute sequentially due to concurrent_pages=1
        # Each task should complete before next starts
        assert execution_order == [
            "start_0",
            "end_0",
            "start_1",
            "end_1",
            "start_2",
            "end_2",
        ]

    async def test_high_rate_allows_fast_execution(self) -> None:
        """Test that high rate limit allows fast execution."""
        limiter = LocalRateLimiter(requests_per_second=100.0, concurrent_pages=10, burst=100)

        start = time.monotonic()

        async def fast_request() -> None:
            async with limiter.acquire():
                pass

        # Make 10 requests - should complete quickly
        await asyncio.gather(*[fast_request() for _ in range(10)])

        elapsed = time.monotonic() - start

        # With burst=100 and rate=100/s, 10 requests should be nearly instant
        assert elapsed < 0.2

    async def test_token_refill_calculation(self) -> None:
        """Test token refill calculation accuracy."""
        limiter = LocalRateLimiter(requests_per_second=5.0, concurrent_pages=10, burst=5)

        # Start with full burst (5 tokens)
        assert limiter._tokens == 5.0

        # Consume all tokens
        async def consume() -> None:
            async with limiter.acquire():
                pass

        await asyncio.gather(*[consume() for _ in range(5)])

        # Tokens should be near 0
        assert limiter._tokens < 0.5

        # Wait 1 second - should get 5 new tokens (5 req/s)
        await asyncio.sleep(1.0)

        # Consume one token to trigger refill
        async with limiter.acquire():
            pass

        # Should have refilled to near max (might be slightly less due to consumption)
        assert limiter._tokens >= 4.0

    async def test_acquire_releases_semaphore_on_cancellation(self) -> None:
        """Test that acquire() releases semaphore when cancelled during token acquisition.

        This test verifies the fix for the semaphore leak when a task is cancelled
        while waiting for rate limit tokens. The semaphore must be released even
        when CancelledError (a BaseException) is raised.
        """
        # Use low rate to force token waiting, high burst initially, concurrent_pages=1
        limiter = LocalRateLimiter(requests_per_second=0.5, concurrent_pages=1, burst=100)

        # Deplete tokens to force next acquire to wait for refill
        for _ in range(100):
            async with limiter.acquire():
                pass

        # Tokens are now depleted
        assert limiter._tokens < 1.0

        # Create a task that will be cancelled during token acquisition
        async def acquire_and_wait() -> None:
            async with limiter.acquire():
                pytest.fail("Should have been cancelled before entering context")

        # Start task - it acquires semaphore, then waits for tokens
        task = asyncio.create_task(acquire_and_wait())

        # Give time to acquire semaphore and start waiting for tokens
        await asyncio.sleep(0.05)

        # Cancel while waiting for tokens
        task.cancel()

        # Verify cancellation
        with pytest.raises(asyncio.CancelledError):
            await task

        # Now verify semaphore was released by checking we can acquire it
        # We'll use a direct semaphore check instead of full acquire
        # to avoid token refill timing issues
        semaphore_acquired = False
        try:
            # Try to acquire semaphore without waiting - should succeed immediately
            # if the cancelled task properly released it
            await asyncio.wait_for(limiter._semaphore.acquire(), timeout=0.1)
            semaphore_acquired = True
            limiter._semaphore.release()
        except TimeoutError:
            # Semaphore was not available - means it wasn't released properly
            semaphore_acquired = False

        assert semaphore_acquired, "Semaphore should have been released when task was cancelled"
