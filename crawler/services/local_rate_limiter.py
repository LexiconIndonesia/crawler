"""Local rate limiter for per-job request throttling.

This module provides in-memory rate limiting for controlling request rates
within a single job execution. Unlike the Redis-based RateLimiter which is
global across all jobs, this limiter enforces limits locally for the current
workflow execution.
"""

import asyncio
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from crawler.core.logging import get_logger

logger = get_logger(__name__)


class LocalRateLimiter:
    """In-memory rate limiter for controlling request rates within a job.

    Supports two types of rate limiting:
    1. requests_per_second: Limits the rate of requests using token bucket algorithm
    2. concurrent_pages: Limits concurrent requests using asyncio.Semaphore

    Example:
        >>> limiter = LocalRateLimiter(requests_per_second=2.0, concurrent_pages=5)
        >>> async with limiter.acquire():
        ...     # Make request - limited to 2 req/s and max 5 concurrent
        ...     response = await client.get(url)
    """

    def __init__(
        self,
        requests_per_second: float = 2.0,
        concurrent_pages: int = 5,
        burst: int = 10,
    ):
        """Initialize local rate limiter.

        Args:
            requests_per_second: Maximum requests per second (0.1-100)
            concurrent_pages: Maximum concurrent requests (1-50)
            burst: Maximum burst requests (1-100)
        """
        self.requests_per_second = max(0.1, min(100.0, requests_per_second))
        self.concurrent_pages = max(1, min(50, concurrent_pages))
        self.burst = max(1, min(100, burst))

        # Semaphore for concurrent requests
        self._semaphore = asyncio.Semaphore(self.concurrent_pages)

        # Token bucket for requests_per_second
        self._tokens = float(self.burst)  # Start with full burst
        self._max_tokens = float(self.burst)
        self._last_update = time.monotonic()
        self._lock = asyncio.Lock()

        logger.info(
            "local_rate_limiter_initialized",
            requests_per_second=self.requests_per_second,
            concurrent_pages=self.concurrent_pages,
            burst=self.burst,
        )

    async def _refill_tokens(self) -> None:
        """Refill tokens based on elapsed time (token bucket algorithm)."""
        now = time.monotonic()
        elapsed = now - self._last_update

        # Add tokens based on elapsed time
        tokens_to_add = elapsed * self.requests_per_second
        self._tokens = min(self._max_tokens, self._tokens + tokens_to_add)
        self._last_update = now

    async def _acquire_token(self) -> None:
        """Acquire a token, waiting if necessary."""
        while True:
            async with self._lock:
                # Refill tokens
                await self._refill_tokens()

                # Check if we have enough tokens
                if self._tokens >= 1.0:
                    # Consume token and exit
                    self._tokens -= 1.0
                    logger.debug("rate_limit_token_acquired", tokens_remaining=self._tokens)
                    return

                # Calculate wait time (we need more tokens)
                tokens_needed = 1.0 - self._tokens
                wait_seconds = tokens_needed / self.requests_per_second

                logger.debug(
                    "rate_limit_waiting",
                    tokens_available=self._tokens,
                    wait_seconds=wait_seconds,
                )

            # Lock is released here (exiting async with context)
            # Sleep outside the lock to allow other coroutines to proceed
            await asyncio.sleep(wait_seconds)
            # Loop back to re-acquire lock and check tokens again

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[None]:
        """Acquire rate limit (both token and semaphore).

        Yields:
            None (context manager)

        Example:
            >>> async with limiter.acquire():
            ...     response = await client.get(url)
        """
        # Acquire semaphore first (limits concurrency)
        await self._semaphore.acquire()

        # Then acquire token (limits rate)
        try:
            await self._acquire_token()
        except BaseException:
            # If token acquisition fails (including cancellation), release semaphore
            self._semaphore.release()
            raise

        try:
            yield
        finally:
            # Always release semaphore on exit
            self._semaphore.release()

    @classmethod
    def from_config(cls, rate_limit_config: dict[str, Any] | None) -> "LocalRateLimiter":
        """Create rate limiter from GlobalConfig.rate_limit dict.

        Args:
            rate_limit_config: GlobalConfig.rate_limit dictionary or None

        Returns:
            LocalRateLimiter instance with configured limits

        Example:
            >>> config = {"requests_per_second": 5.0, "concurrent_pages": 10, "burst": 20}
            >>> limiter = LocalRateLimiter.from_config(config)
        """
        if not rate_limit_config or not isinstance(rate_limit_config, dict):
            # No config - use defaults
            return cls()

        return cls(
            requests_per_second=rate_limit_config.get("requests_per_second", 2.0),
            concurrent_pages=rate_limit_config.get("concurrent_pages", 5),
            burst=rate_limit_config.get("burst", 10),
        )
