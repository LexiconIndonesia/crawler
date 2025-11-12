"""Browser pool manager for Playwright browser automation.

Manages a pool of browser instances and contexts for efficient browser automation.
Supports configurable pool size, context management, health checks, and graceful shutdown.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from config import Settings
from crawler.core.logging import get_logger
from crawler.core.metrics import (
    browser_crash_recoveries_total,
    browser_crashes_total,
    browser_pool_contexts_available,
    browser_pool_healthy,
    browser_pool_queue_size,
    browser_pool_queue_wait_seconds,
    browser_pool_size,
    browser_sessions_active,
)

logger = get_logger(__name__)

BrowserType = Literal["chromium", "firefox", "webkit"]

__all__ = ["BrowserPool", "BrowserInstance", "BrowserCrashError", "BrowserType"]


class BrowserCrashError(Exception):
    """Raised when a browser crashes during operation."""

    def __init__(self, message: str, browser_type: BrowserType):
        """Initialize browser crash error.

        Args:
            message: Error message describing the crash
            browser_type: Type of browser that crashed
        """
        super().__init__(message)
        self.browser_type = browser_type


@dataclass
class BrowserInstance:
    """Wrapper for a browser instance with metadata."""

    browser: Browser
    browser_type: BrowserType
    created_at: datetime
    active_contexts: int = 0
    max_contexts: int = 5
    is_healthy: bool = True
    last_health_check: datetime | None = None
    recovery_attempts: int = 0
    last_recovery_attempt: datetime | None = None
    crash_timestamp: datetime | None = None  # Track when browser first crashed

    def can_create_context(self) -> bool:
        """Check if browser can create a new context.

        Returns:
            True if browser has capacity for more contexts, False otherwise.
        """
        return self.is_healthy and self.active_contexts < self.max_contexts

    def is_in_recovery_backoff(self, backoff_base: float, now: datetime) -> bool:
        """Check if browser is in recovery backoff period.

        Args:
            backoff_base: Base multiplier for exponential backoff
            now: Current timestamp

        Returns:
            True if still in backoff period, False if ready for retry
        """
        # Guard: never attempted recovery
        if self.last_recovery_attempt is None:
            return False

        # Calculate backoff duration: base^attempt seconds
        backoff_seconds = backoff_base**self.recovery_attempts
        next_attempt_time = self.last_recovery_attempt.timestamp() + backoff_seconds

        return now.timestamp() < next_attempt_time


class BrowserPool:
    """Manages a pool of browser instances for efficient automation.

    Features:
    - Configurable pool size (number of browser instances)
    - Context management (multiple contexts per browser)
    - Health checks for browser instances
    - Graceful shutdown with resource cleanup
    - Prometheus metrics integration

    Usage:
        pool = BrowserPool(settings)
        await pool.initialize()
        async with pool.acquire_context() as context:
            # Use context for automation
            pass
        await pool.shutdown()
    """

    def __init__(self, settings: Settings):
        """Initialize browser pool manager.

        Args:
            settings: Application settings with pool configuration.
        """
        self.settings = settings
        self.pool_size = settings.browser_pool_size
        self.max_contexts_per_browser = settings.browser_max_contexts_per_browser
        self.context_timeout = settings.browser_context_timeout
        self.health_check_interval = settings.browser_health_check_interval
        self.default_browser_type = settings.browser_default_type
        self.max_recovery_attempts = settings.browser_max_recovery_attempts
        self.recovery_backoff_base = settings.browser_recovery_backoff_base

        # Pool state
        self._playwright: Playwright | None = None
        self._browsers: list[BrowserInstance] = []
        self._context_semaphore = asyncio.Semaphore(self.pool_size * self.max_contexts_per_browser)
        self._lock = asyncio.Lock()
        self._initialized = False
        self._shutting_down = False
        self._health_check_task: asyncio.Task[None] | None = None

    async def initialize(self) -> None:
        """Initialize the browser pool by launching browser instances.

        Creates N browser instances on startup where N is configured by pool_size.
        Starts the health check background task.

        Raises:
            RuntimeError: If pool is already initialized or playwright fails.
        """
        # Guard: already initialized
        if self._initialized:
            logger.warning("browser_pool_already_initialized")
            return

        try:
            logger.info(
                "browser_pool_initializing",
                pool_size=self.pool_size,
                max_contexts_per_browser=self.max_contexts_per_browser,
                browser_type=self.default_browser_type,
            )

            # Start playwright
            self._playwright = await async_playwright().start()

            # Launch browser instances
            for i in range(self.pool_size):
                browser = await self._launch_browser(self.default_browser_type)
                instance = BrowserInstance(
                    browser=browser,
                    browser_type=self.default_browser_type,
                    created_at=datetime.now(UTC),
                    max_contexts=self.max_contexts_per_browser,
                )
                self._browsers.append(instance)
                logger.info(
                    "browser_instance_launched",
                    index=i,
                    browser_type=self.default_browser_type,
                )

            # Start health check background task
            self._health_check_task = asyncio.create_task(self._health_check_loop())

            self._initialized = True

            # Update metrics
            browser_pool_size.set(len(self._browsers))
            browser_pool_healthy.set(len(self._browsers))
            # Use actual browser count for consistency
            browser_pool_contexts_available.set(len(self._browsers) * self.max_contexts_per_browser)

            logger.info("browser_pool_initialized", total_browsers=len(self._browsers))

        except Exception as e:
            logger.error("browser_pool_init_error", error=str(e))
            # Clean up any partially created resources
            await self._cleanup_all_browsers()

            # Stop playwright if it was started
            if self._playwright is not None:
                try:
                    await self._playwright.stop()
                    logger.debug("playwright_stopped_after_init_error")
                except Exception as cleanup_error:
                    logger.debug("playwright_stop_error_during_cleanup", error=str(cleanup_error))
                finally:
                    self._playwright = None

            raise RuntimeError(f"Failed to initialize browser pool: {e}") from e

    async def _launch_browser(self, browser_type: BrowserType) -> Browser:
        """Launch a browser instance.

        Args:
            browser_type: Type of browser to launch (chromium, firefox, webkit).

        Returns:
            Launched browser instance.

        Raises:
            RuntimeError: If playwright is not initialized or browser launch fails.
        """
        # Guard: playwright not initialized
        if self._playwright is None:
            raise RuntimeError("Playwright not initialized")

        try:
            if browser_type == "firefox":
                browser = await self._playwright.firefox.launch()
            elif browser_type == "webkit":
                browser = await self._playwright.webkit.launch()
            else:
                browser = await self._playwright.chromium.launch()

            return browser
        except Exception as e:
            logger.error("browser_launch_error", browser_type=browser_type, error=str(e))
            raise RuntimeError(f"Failed to launch {browser_type} browser: {e}") from e

    async def _remove_and_replace_browser(self, crashed_instance: BrowserInstance) -> None:
        """Remove a crashed browser and replace it with a new one.

        This method implements exponential backoff and max retry limits:
        1. Logs the crash event (increments crash metric only on first crash)
        2. Checks if max recovery attempts exceeded
        3. Checks if still in backoff period
        4. Removes the crashed browser from the pool
        5. Attempts to close the crashed browser (best effort)
        6. Launches a new browser to replace it
        7. On success: resets recovery tracking
        8. On failure: increments attempts, updates backoff, restores instance

        Args:
            crashed_instance: The browser instance that crashed

        Note:
            This method should be called while holding the _lock to ensure thread safety.
        """
        browser_index = (
            self._browsers.index(crashed_instance) if crashed_instance in self._browsers else -1
        )
        browser_type = crashed_instance.browser_type
        now = datetime.now(UTC)

        # Track first crash for this instance (increment metric only once per crash)
        if crashed_instance.crash_timestamp is None:
            crashed_instance.crash_timestamp = now
            browser_crashes_total.labels(browser_type=browser_type).inc()
            logger.error(
                "browser_crashed_detected",
                browser_index=browser_index,
                browser_type=browser_type,
                active_contexts=crashed_instance.active_contexts,
            )

        # Guard: max recovery attempts exceeded - permanently remove
        if crashed_instance.recovery_attempts >= self.max_recovery_attempts:
            if crashed_instance in self._browsers:
                # Calculate capacity before removal
                previous_capacity = len(self._browsers) * self.max_contexts_per_browser

                self._browsers.remove(crashed_instance)
                logger.warning(
                    "browser_permanently_removed_max_attempts",
                    browser_index=browser_index,
                    browser_type=browser_type,
                    recovery_attempts=crashed_instance.recovery_attempts,
                    max_attempts=self.max_recovery_attempts,
                )

                # Try to close the crashed browser (best effort)
                try:
                    await crashed_instance.browser.close()
                except Exception as e:
                    logger.debug("crashed_browser_close_error", error=str(e))

                # Recompute capacity after removal
                new_capacity = len(self._browsers) * self.max_contexts_per_browser
                capacity_delta = previous_capacity - new_capacity

                # Adjust semaphore to reflect reduced capacity
                # We "consume" the delta permits by acquiring them without releasing
                # Ensures semaphore never hands out more permits than browsers can serve
                permits_consumed = 0
                if capacity_delta > 0:
                    for _ in range(capacity_delta):
                        # Try non-blocking acquire
                        if self._context_semaphore.locked():
                            # All permits already consumed
                            break
                        try:
                            # Use asyncio.wait_for with 0 timeout for non-blocking behavior
                            await asyncio.wait_for(self._context_semaphore.acquire(), timeout=0.0)
                            permits_consumed += 1
                        except TimeoutError:
                            # No permits available, stop trying
                            break

                    logger.info(
                        "browser_pool_capacity_reduced",
                        previous_capacity=previous_capacity,
                        new_capacity=new_capacity,
                        capacity_delta=capacity_delta,
                        permits_consumed=permits_consumed,
                    )

                # Update metrics
                browser_pool_size.set(len(self._browsers))
                healthy_count = sum(1 for b in self._browsers if b.is_healthy)
                browser_pool_healthy.set(healthy_count)

                # Update available contexts metric with new capacity
                total_contexts = sum(b.active_contexts for b in self._browsers)
                available_contexts = max(0, new_capacity - total_contexts)
                browser_pool_contexts_available.set(available_contexts)

            msg = (
                f"Browser permanently removed after {self.max_recovery_attempts} "
                "failed recovery attempts"
            )
            raise BrowserCrashError(msg, browser_type=browser_type)

        # Guard: still in backoff period - skip recovery
        if crashed_instance.is_in_recovery_backoff(self.recovery_backoff_base, now):
            backoff_seconds = self.recovery_backoff_base**crashed_instance.recovery_attempts
            next_attempt = (
                crashed_instance.last_recovery_attempt.timestamp() + backoff_seconds
                if crashed_instance.last_recovery_attempt
                else now.timestamp()
            )
            logger.debug(
                "browser_recovery_skipped_backoff",
                browser_index=browser_index,
                browser_type=browser_type,
                recovery_attempts=crashed_instance.recovery_attempts,
                next_attempt_in_seconds=next_attempt - now.timestamp(),
            )
            raise BrowserCrashError(
                "Browser recovery skipped - still in backoff period",
                browser_type=browser_type,
            )

        # Remove crashed browser from pool for replacement attempt
        if crashed_instance in self._browsers:
            self._browsers.remove(crashed_instance)
            logger.info(
                "crashed_browser_removed_for_recovery",
                browser_index=browser_index,
                remaining_browsers=len(self._browsers),
                recovery_attempt=crashed_instance.recovery_attempts + 1,
            )

        # Try to close the crashed browser (best effort)
        try:
            await crashed_instance.browser.close()
        except Exception as e:
            logger.debug("crashed_browser_close_error", error=str(e))

        # Increment recovery attempts and update timestamp
        crashed_instance.recovery_attempts += 1
        crashed_instance.last_recovery_attempt = now

        # Launch replacement browser
        try:
            new_browser = await self._launch_browser(browser_type)
            new_instance = BrowserInstance(
                browser=new_browser,
                browser_type=browser_type,
                created_at=now,
                max_contexts=self.max_contexts_per_browser,
            )
            self._browsers.append(new_instance)

            # Increment recovery metric
            browser_crash_recoveries_total.inc()

            logger.info(
                "browser_crash_recovery_successful",
                browser_type=browser_type,
                new_browser_index=len(self._browsers) - 1,
                recovery_attempt=crashed_instance.recovery_attempts,
            )

            # Update metrics
            browser_pool_size.set(len(self._browsers))
            healthy_count = sum(1 for b in self._browsers if b.is_healthy)
            browser_pool_healthy.set(healthy_count)

        except Exception as e:
            backoff_seconds = self.recovery_backoff_base**crashed_instance.recovery_attempts
            logger.error(
                "browser_crash_recovery_failed",
                browser_type=browser_type,
                error=str(e),
                recovery_attempt=crashed_instance.recovery_attempts,
                next_retry_in_seconds=backoff_seconds,
            )

            # Restore crashed instance so pool size & semaphore stay consistent
            if crashed_instance not in self._browsers:
                crashed_instance.is_healthy = False
                if 0 <= browser_index <= len(self._browsers):
                    self._browsers.insert(browser_index, crashed_instance)
                else:
                    self._browsers.append(crashed_instance)

            browser_pool_size.set(len(self._browsers))
            healthy_count = sum(1 for b in self._browsers if b.is_healthy)
            browser_pool_healthy.set(healthy_count)

            # Re-raise as BrowserCrashError to signal pool degradation
            msg = (
                f"Failed to recover from browser crash "
                f"(attempt {crashed_instance.recovery_attempts}/"
                f"{self.max_recovery_attempts}): {e}"
            )
            raise BrowserCrashError(msg, browser_type=browser_type) from e

    @asynccontextmanager
    async def acquire_context(self, timeout: float | None = None) -> AsyncIterator[BrowserContext]:
        """Acquire a browser context from the pool.

        This is a context manager that automatically releases the context when done.

        Args:
            timeout: Optional timeout in seconds for acquiring a context.
                    Defaults to settings.browser_context_timeout.

        Yields:
            BrowserContext for use in automation.

        Raises:
            RuntimeError: If pool is not initialized or shutting down.
            TimeoutError: If context cannot be acquired within timeout.

        Example:
            async with pool.acquire_context() as context:
                page = await context.new_page()
                await page.goto("https://example.com")
        """
        # Guard: pool not initialized
        if not self._initialized:
            raise RuntimeError("Browser pool not initialized. Call initialize() first.")

        # Guard: pool shutting down
        if self._shutting_down:
            raise RuntimeError("Browser pool is shutting down")

        timeout = timeout or self.context_timeout
        browser_instance: BrowserInstance | None = None
        context: BrowserContext | None = None
        semaphore_acquired = False
        context_created = False  # Track if context was successfully created
        queue_start_time = datetime.now(UTC)

        try:
            # Check if we need to queue (all contexts in use)
            # Use actual browser count, not initial pool_size (may have removed crashed browsers)
            currently_available = len(self._browsers) * self.max_contexts_per_browser
            currently_in_use = sum(b.active_contexts for b in self._browsers)
            will_queue = currently_in_use >= currently_available

            if will_queue:
                # Update queue metric - we're about to wait
                browser_pool_queue_size.inc()
                logger.info(
                    "context_request_queued",
                    queue_position=self._context_semaphore._value,
                    timeout=timeout,
                )

            # Wait for available slot with timeout (FIFO queue via semaphore)
            try:
                await asyncio.wait_for(
                    self._context_semaphore.acquire(),
                    timeout=timeout,
                )
                semaphore_acquired = True

                # Calculate queue wait time
                queue_wait_time = (datetime.now(UTC) - queue_start_time).total_seconds()
                if will_queue:
                    browser_pool_queue_size.dec()
                    browser_pool_queue_wait_seconds.observe(queue_wait_time)
                    logger.info(
                        "context_acquired_from_queue",
                        queue_wait_seconds=queue_wait_time,
                    )

            except TimeoutError:
                # Remove from queue metrics if we timed out
                if will_queue:
                    browser_pool_queue_size.dec()
                logger.error("context_acquire_timeout", timeout=timeout)
                raise TimeoutError(f"Failed to acquire browser context within {timeout}s") from None

            # Get a browser instance with capacity
            browser_instance = await self._get_available_browser()

            # Guard: no available browser
            if browser_instance is None:
                raise RuntimeError("No healthy browser instances available")

            # Create context - handle potential browser crash during creation
            try:
                context = await browser_instance.browser.new_context()
            except Exception as e:
                # Check if this is a browser crash
                # First check browser connection status (most reliable)
                is_crash = False
                try:
                    if not browser_instance.browser.is_connected():
                        is_crash = True
                except Exception:
                    pass  # If we can't check, fall back to keyword matching

                # Fall back to keyword matching if connection check didn't detect crash
                if not is_crash:
                    error_msg = str(e).lower()
                    crash_keywords = [
                        "connection",
                        "closed",
                        "disconnected",
                        "target closed",
                        "browser closed",
                    ]
                    is_crash = any(keyword in error_msg for keyword in crash_keywords)

                if is_crash:
                    browser_idx = (
                        self._browsers.index(browser_instance)
                        if browser_instance in self._browsers
                        else None
                    )
                    logger.error(
                        "browser_crash_during_context_creation",
                        browser_index=browser_idx,
                        error=str(e),
                    )

                    # Mark browser as unhealthy and attempt recovery
                    async with self._lock:
                        browser_instance.is_healthy = False
                        try:
                            await self._remove_and_replace_browser(browser_instance)
                        except BrowserCrashError:
                            # Recovery failed, but we already released the semaphore
                            pass

                    # Re-raise as BrowserCrashError
                    raise BrowserCrashError(
                        "Browser crashed during context creation",
                        browser_type=browser_instance.browser_type,
                    ) from e
                else:
                    # Not a crash, just a transient error
                    raise

            # Mark context as successfully created and update metrics
            # IMPORTANT: Only update counters AFTER context creation succeeds
            async with self._lock:
                browser_instance.active_contexts += 1
                context_created = True  # Set flag only after increment succeeds
                total_contexts = sum(b.active_contexts for b in self._browsers)
                browser_sessions_active.set(total_contexts)
                # Use actual browser count, not initial pool_size
                current_capacity = len(self._browsers) * self.max_contexts_per_browser
                available_contexts = current_capacity - total_contexts
                browser_pool_contexts_available.set(available_contexts)

            logger.debug(
                "context_acquired",
                browser_index=self._browsers.index(browser_instance),
                active_contexts=browser_instance.active_contexts,
            )

            yield context

        except Exception as e:
            logger.error("context_acquire_error", error=str(e))
            raise
        finally:
            # Clean and release context (only if it was created)
            if context is not None:
                # Clean context state before closing
                await self._cleanup_context(context)

                # Close the context
                try:
                    await context.close()
                except Exception as e:
                    logger.debug("context_close_error", error=str(e))

            # Update metrics - ONLY decrement if we successfully incremented
            if context_created and browser_instance is not None:
                async with self._lock:
                    browser_instance.active_contexts -= 1
                    total_contexts = sum(b.active_contexts for b in self._browsers)
                    browser_sessions_active.set(total_contexts)
                    # Use actual browser count, not initial pool_size
                    available_contexts = (
                        len(self._browsers) * self.max_contexts_per_browser - total_contexts
                    )
                    browser_pool_contexts_available.set(available_contexts)

            # Release semaphore only if it was acquired
            if semaphore_acquired:
                self._context_semaphore.release()

            # Calculate browser_index safely (instance may have been removed due to crash)
            browser_index: int | None = None
            if browser_instance:
                try:
                    browser_index = self._browsers.index(browser_instance)
                except ValueError:
                    browser_index = None  # Browser was removed (e.g., crash recovery)

            logger.debug(
                "context_released",
                browser_index=browser_index,
            )

    async def _cleanup_context(self, context: BrowserContext) -> None:
        """Clean context state before returning to pool or closing.

        Clears cookies, storage, and closes all pages except about:blank to ensure
        clean state for next use or proper disposal.

        Args:
            context: Browser context to clean

        Note:
            All cleanup operations are wrapped in try/except to ensure partial
            failures don't prevent the context from being closed.
        """
        try:
            # Clear cookies
            try:
                await context.clear_cookies()
                logger.debug("context_cookies_cleared")
            except Exception as e:
                logger.debug("context_clear_cookies_error", error=str(e))

            # Clear storage (localStorage, sessionStorage, etc.)
            try:
                # Close all pages first
                pages = context.pages
                for page in pages:
                    try:
                        # Clear storage for this page
                        await page.evaluate(
                            """() => {
                                localStorage.clear();
                                sessionStorage.clear();
                            }"""
                        )
                    except Exception as e:
                        logger.debug("page_storage_clear_error", error=str(e))

                    # Close the page
                    try:
                        await page.close()
                    except Exception as e:
                        logger.debug("page_close_error_during_cleanup", error=str(e))

                logger.debug("context_storage_cleared", pages_closed=len(pages))

            except Exception as e:
                logger.debug("context_clear_storage_error", error=str(e))

            # Create a clean about:blank page if context is still open
            # This ensures the context is in a known state
            try:
                if not context.pages:
                    await context.new_page()
                    logger.debug("context_reset_to_blank")
            except Exception as e:
                logger.debug("context_reset_error", error=str(e))

        except Exception as e:
            # Catch-all for any unexpected errors during cleanup
            logger.warning("context_cleanup_failed", error=str(e))

    async def _get_available_browser(self) -> BrowserInstance | None:
        """Get a browser instance with available context capacity.

        Returns:
            BrowserInstance with capacity, or None if all are at capacity.
        """
        async with self._lock:
            # Try to find a healthy browser with capacity
            for browser_instance in self._browsers:
                if browser_instance.can_create_context():
                    return browser_instance

            # No browsers with capacity
            logger.warning(
                "no_available_browsers",
                total_browsers=len(self._browsers),
                active_contexts=[b.active_contexts for b in self._browsers],
            )
            return None

    async def health_check(self) -> dict[str, Any]:
        """Perform health check on all browser instances.

        Checks each browser by creating and closing a test context.
        Updates the is_healthy flag for each browser instance.

        Returns:
            Dict with health check results:
            {
                "total_browsers": int,
                "healthy_browsers": int,
                "unhealthy_browsers": int,
                "total_contexts": int,
                "browsers": [{"index": int, "healthy": bool, "contexts": int}, ...]
            }
        """
        # Guard: pool not initialized
        if not self._initialized:
            return {
                "total_browsers": 0,
                "healthy_browsers": 0,
                "unhealthy_browsers": 0,
                "total_contexts": 0,
                "browsers": [],
            }

        logger.debug("browser_pool_health_check_starting")

        # Step 1: Snapshot browser instances while holding lock
        async with self._lock:
            browser_snapshot = [
                (i, browser_instance) for i, browser_instance in enumerate(self._browsers)
            ]

        # Step 2: Check health WITHOUT holding lock (parallel async operations)
        health_results = []
        for i, browser_instance in browser_snapshot:
            is_healthy, is_crashed = await self._check_browser_health(browser_instance)
            health_results.append((i, browser_instance, is_healthy, is_crashed))

        # Step 3: Update shared state and handle crashes while holding lock
        healthy_count = 0
        browser_statuses = []
        crashed_browsers = []

        async with self._lock:
            now = datetime.now(UTC)
            for i, browser_instance, is_healthy, is_crashed in health_results:
                # Update health status
                browser_instance.is_healthy = is_healthy
                browser_instance.last_health_check = now

                if is_healthy:
                    healthy_count += 1
                elif is_crashed:
                    # Mark for crash recovery
                    crashed_browsers.append(browser_instance)

                browser_statuses.append(
                    {
                        "index": i,
                        "healthy": is_healthy,
                        "crashed": is_crashed,
                        "contexts": browser_instance.active_contexts,
                        "browser_type": browser_instance.browser_type,
                    }
                )

            # Handle crashed browsers - remove and replace (respecting backoff)
            for crashed_instance in crashed_browsers:
                # Skip if in backoff period
                if crashed_instance.is_in_recovery_backoff(self.recovery_backoff_base, now):
                    backoff_seconds = self.recovery_backoff_base**crashed_instance.recovery_attempts
                    next_attempt = (
                        crashed_instance.last_recovery_attempt.timestamp() + backoff_seconds
                        if crashed_instance.last_recovery_attempt
                        else now.timestamp()
                    )
                    logger.debug(
                        "crash_recovery_skipped_in_backoff",
                        browser_type=crashed_instance.browser_type,
                        recovery_attempts=crashed_instance.recovery_attempts,
                        next_attempt_in_seconds=next_attempt - now.timestamp(),
                    )
                    continue

                try:
                    await self._remove_and_replace_browser(crashed_instance)
                except BrowserCrashError as e:
                    logger.debug(
                        "crash_recovery_failed_during_health_check",
                        error=str(e),
                        browser_type=e.browser_type,
                    )
                    # Continue with other browsers even if one recovery fails

            # Recalculate aggregate metrics while holding lock
            total_contexts = sum(b.active_contexts for b in self._browsers)
            total_browsers = len(self._browsers)

        result = {
            "total_browsers": total_browsers,
            "healthy_browsers": healthy_count,
            "unhealthy_browsers": total_browsers - healthy_count,
            "total_contexts": total_contexts,
            "browsers": browser_statuses,
        }

        # Update health metric
        browser_pool_healthy.set(healthy_count)

        logger.info(
            "browser_pool_health_check_completed",
            healthy=healthy_count,
            unhealthy=len(self._browsers) - healthy_count,
        )

        return result

    async def _check_browser_health(self, browser_instance: BrowserInstance) -> tuple[bool, bool]:
        """Check if a browser instance is healthy.

        Args:
            browser_instance: Browser instance to check.

        Returns:
            Tuple of (is_healthy, is_crashed):
            - is_healthy: True if browser is healthy, False otherwise
            - is_crashed: True if browser has crashed and needs replacement, False otherwise
        """
        try:
            # Try to check if browser is connected
            if not browser_instance.browser.is_connected():
                logger.warning("browser_not_connected")
                # Browser disconnection is a sign of crash
                return (False, True)

            # Try to create and close a test context
            test_context = await browser_instance.browser.new_context()
            await test_context.close()
            return (True, False)

        except Exception as e:
            logger.warning("browser_health_check_failed", error=str(e))
            # Determine if this is a crash or transient error
            # First check browser connection status (most reliable)
            is_crash = False
            try:
                if not browser_instance.browser.is_connected():
                    is_crash = True
            except Exception:
                pass  # If we can't check, fall back to keyword matching

            # Fall back to keyword matching if connection check didn't detect crash
            if not is_crash:
                error_msg = str(e).lower()
                crash_keywords = [
                    "connection",
                    "closed",
                    "disconnected",
                    "target closed",
                    "browser closed",
                ]
                is_crash = any(keyword in error_msg for keyword in crash_keywords)

            return (False, is_crash)

    async def _health_check_loop(self) -> None:
        """Background task that runs periodic health checks."""
        logger.info(
            "browser_health_check_loop_started",
            interval=self.health_check_interval,
        )

        while not self._shutting_down:
            try:
                await asyncio.sleep(self.health_check_interval)
                await self.health_check()
            except Exception as e:
                logger.error("health_check_loop_error", error=str(e))

        logger.info("browser_health_check_loop_stopped")

    async def shutdown(self) -> None:
        """Gracefully shutdown the browser pool.

        Closes all browser contexts and instances, stops health checks,
        and releases all resources.
        """
        # Guard: not initialized
        if not self._initialized:
            logger.warning("browser_pool_not_initialized_for_shutdown")
            return

        # Guard: already shutting down
        if self._shutting_down:
            logger.warning("browser_pool_already_shutting_down")
            return

        logger.info("browser_pool_shutdown_starting")
        self._shutting_down = True

        # Stop health check task
        if self._health_check_task is not None:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass

        # Close all browsers
        await self._cleanup_all_browsers()

        # Stop playwright
        if self._playwright is not None:
            try:
                await self._playwright.stop()
            except Exception as e:
                logger.debug("playwright_stop_error", error=str(e))

        # Reset metrics
        browser_sessions_active.set(0)
        browser_pool_size.set(0)
        browser_pool_healthy.set(0)
        browser_pool_contexts_available.set(0)
        browser_pool_queue_size.set(0)

        self._initialized = False
        self._shutting_down = False

        logger.info("browser_pool_shutdown_completed")

    async def _cleanup_all_browsers(self) -> None:
        """Close all browser instances."""
        for i, browser_instance in enumerate(self._browsers):
            try:
                await browser_instance.browser.close()
                logger.debug("browser_closed", index=i)
            except Exception as e:
                logger.debug("browser_close_error", index=i, error=str(e))

        self._browsers.clear()

    def get_pool_stats(self) -> dict[str, Any]:
        """Get current pool statistics.

        Returns:
            Dict with pool statistics:
            {
                "pool_size": int,
                "total_browsers": int,
                "total_contexts": int,
                "max_contexts": int,
                "initialized": bool,
                "shutting_down": bool,
            }
        """
        total_contexts = sum(b.active_contexts for b in self._browsers)
        # Use actual browser count for max_contexts (may differ from pool_size if browsers removed)
        max_contexts = len(self._browsers) * self.max_contexts_per_browser

        return {
            "pool_size": self.pool_size,  # Original configured size
            "total_browsers": len(self._browsers),  # Actual current browser count
            "total_contexts": total_contexts,
            "max_contexts": max_contexts,
            "initialized": self._initialized,
            "shutting_down": self._shutting_down,
        }
