"""Unit tests for BrowserPool."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from crawler.services.browser_pool import BrowserCrashError, BrowserInstance, BrowserPool


@pytest.fixture
def settings():
    """Create test settings."""
    return Settings(
        browser_pool_size=2,
        browser_max_contexts_per_browser=3,
        browser_context_timeout=60,
        browser_health_check_interval=30,
        browser_default_type="chromium",
    )


@pytest.fixture
def mock_playwright():
    """Create mock playwright."""
    with patch("crawler.services.browser_pool.async_playwright") as mock:
        playwright = AsyncMock()
        mock.return_value.start = AsyncMock(return_value=playwright)

        # Mock browser instances
        browser = AsyncMock()
        browser.is_connected = MagicMock(return_value=True)
        browser.new_context = AsyncMock()
        browser.close = AsyncMock()

        # Mock browser types
        playwright.chromium.launch = AsyncMock(return_value=browser)
        playwright.firefox.launch = AsyncMock(return_value=browser)
        playwright.webkit.launch = AsyncMock(return_value=browser)
        playwright.stop = AsyncMock()

        yield playwright


class TestBrowserInstance:
    """Tests for BrowserInstance dataclass."""

    def test_browser_instance_creation(self):
        """Test creating a BrowserInstance."""
        browser = MagicMock()
        instance = BrowserInstance(
            browser=browser,
            browser_type="chromium",
            created_at=MagicMock(),
            max_contexts=5,
        )

        assert instance.browser == browser
        assert instance.browser_type == "chromium"
        assert instance.active_contexts == 0
        assert instance.max_contexts == 5
        assert instance.is_healthy is True
        assert instance.last_health_check is None

    def test_can_create_context_available(self):
        """Test can_create_context when contexts are available."""
        browser = MagicMock()
        instance = BrowserInstance(
            browser=browser,
            browser_type="chromium",
            created_at=MagicMock(),
            max_contexts=5,
        )
        instance.active_contexts = 2

        assert instance.can_create_context() is True

    def test_can_create_context_at_capacity(self):
        """Test can_create_context when at capacity."""
        browser = MagicMock()
        instance = BrowserInstance(
            browser=browser,
            browser_type="chromium",
            created_at=MagicMock(),
            max_contexts=5,
        )
        instance.active_contexts = 5

        assert instance.can_create_context() is False

    def test_can_create_context_unhealthy(self):
        """Test can_create_context when browser is unhealthy."""
        browser = MagicMock()
        instance = BrowserInstance(
            browser=browser,
            browser_type="chromium",
            created_at=MagicMock(),
            max_contexts=5,
        )
        instance.is_healthy = False

        assert instance.can_create_context() is False


class TestBrowserPool:
    """Tests for BrowserPool."""

    def test_browser_pool_creation(self, settings):
        """Test creating a BrowserPool."""
        pool = BrowserPool(settings)

        assert pool.pool_size == 2
        assert pool.max_contexts_per_browser == 3
        assert pool.context_timeout == 60
        assert pool.health_check_interval == 30
        assert pool.default_browser_type == "chromium"
        assert pool._initialized is False
        assert pool._shutting_down is False

    @pytest.mark.asyncio
    async def test_initialize_pool(self, settings, mock_playwright):
        """Test initializing the browser pool."""
        pool = BrowserPool(settings)

        await pool.initialize()

        assert pool._initialized is True
        assert len(pool._browsers) == 2
        assert pool._playwright is not None
        assert pool._health_check_task is not None

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_initialize_already_initialized(self, settings, mock_playwright):
        """Test initializing an already initialized pool."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Try to initialize again
        await pool.initialize()

        # Should still have 2 browsers (not double initialized)
        assert len(pool._browsers) == 2

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_launch_browser_chromium(self, settings, mock_playwright):
        """Test launching a chromium browser."""
        pool = BrowserPool(settings)
        pool._playwright = mock_playwright

        browser = await pool._launch_browser("chromium")

        assert browser is not None
        mock_playwright.chromium.launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_browser_firefox(self, settings, mock_playwright):
        """Test launching a firefox browser."""
        pool = BrowserPool(settings)
        pool._playwright = mock_playwright

        browser = await pool._launch_browser("firefox")

        assert browser is not None
        mock_playwright.firefox.launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_browser_webkit(self, settings, mock_playwright):
        """Test launching a webkit browser."""
        pool = BrowserPool(settings)
        pool._playwright = mock_playwright

        browser = await pool._launch_browser("webkit")

        assert browser is not None
        mock_playwright.webkit.launch.assert_called_once()

    @pytest.mark.asyncio
    async def test_launch_browser_without_playwright(self, settings):
        """Test launching browser without playwright initialized."""
        pool = BrowserPool(settings)
        pool._playwright = None

        with pytest.raises(RuntimeError, match="Playwright not initialized"):
            await pool._launch_browser("chromium")

    @pytest.mark.asyncio
    async def test_acquire_context_success(self, settings, mock_playwright):
        """Test acquiring a browser context successfully."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context
        mock_context = AsyncMock()
        pool._browsers[0].browser.new_context = AsyncMock(return_value=mock_context)

        async with pool.acquire_context() as context:
            assert context == mock_context
            assert pool._browsers[0].active_contexts == 1

        # After context is released
        assert pool._browsers[0].active_contexts == 0

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_context_not_initialized(self, settings):
        """Test acquiring context when pool is not initialized."""
        pool = BrowserPool(settings)

        with pytest.raises(RuntimeError, match="Browser pool not initialized"):
            async with pool.acquire_context():
                pass

    @pytest.mark.asyncio
    async def test_acquire_context_shutting_down(self, settings, mock_playwright):
        """Test acquiring context when pool is shutting down."""
        pool = BrowserPool(settings)
        await pool.initialize()
        pool._shutting_down = True

        with pytest.raises(RuntimeError, match="Browser pool is shutting down"):
            async with pool.acquire_context():
                pass

        # Clean up
        pool._shutting_down = False
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_get_available_browser_success(self, settings, mock_playwright):
        """Test getting an available browser."""
        pool = BrowserPool(settings)
        await pool.initialize()

        browser_instance = await pool._get_available_browser()

        assert browser_instance is not None
        assert browser_instance.can_create_context() is True

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_get_available_browser_all_at_capacity(self, settings, mock_playwright):
        """Test getting browser when all are at capacity."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Fill up all browsers
        for browser in pool._browsers:
            browser.active_contexts = browser.max_contexts

        browser_instance = await pool._get_available_browser()

        assert browser_instance is None

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_health_check(self, settings, mock_playwright):
        """Test performing health check."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock health check
        for browser in pool._browsers:
            browser.browser.is_connected = MagicMock(return_value=True)
            browser.browser.new_context = AsyncMock()

        result = await pool.health_check()

        assert result["total_browsers"] == 2
        assert result["healthy_browsers"] == 2
        assert result["unhealthy_browsers"] == 0
        assert len(result["browsers"]) == 2

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_not_initialized(self, settings):
        """Test health check when pool is not initialized."""
        pool = BrowserPool(settings)

        result = await pool.health_check()

        assert result["total_browsers"] == 0
        assert result["healthy_browsers"] == 0
        assert result["unhealthy_browsers"] == 0

    @pytest.mark.asyncio
    async def test_check_browser_health_healthy(self, settings, mock_playwright):
        """Test checking browser health when browser is healthy."""
        pool = BrowserPool(settings)
        await pool.initialize()

        browser_instance = pool._browsers[0]
        browser_instance.browser.is_connected = MagicMock(return_value=True)
        mock_context = AsyncMock()
        browser_instance.browser.new_context = AsyncMock(return_value=mock_context)

        is_healthy, is_crashed = await pool._check_browser_health(browser_instance)

        assert is_healthy is True
        assert is_crashed is False
        mock_context.close.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_check_browser_health_not_connected(self, settings, mock_playwright):
        """Test checking browser health when browser is not connected."""
        pool = BrowserPool(settings)
        await pool.initialize()

        browser_instance = pool._browsers[0]
        browser_instance.browser.is_connected = MagicMock(return_value=False)

        is_healthy, is_crashed = await pool._check_browser_health(browser_instance)

        assert is_healthy is False
        assert is_crashed is True

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_check_browser_health_exception(self, settings, mock_playwright):
        """Test checking browser health when exception occurs."""
        pool = BrowserPool(settings)
        await pool.initialize()

        browser_instance = pool._browsers[0]
        browser_instance.browser.is_connected = MagicMock(side_effect=Exception("Connection error"))

        is_healthy, is_crashed = await pool._check_browser_health(browser_instance)

        assert is_healthy is False
        assert is_crashed is True

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_shutdown(self, settings, mock_playwright):
        """Test shutting down the browser pool."""
        pool = BrowserPool(settings)
        await pool.initialize()

        assert pool._initialized is True

        await pool.shutdown()

        assert pool._initialized is False
        assert pool._shutting_down is False
        assert len(pool._browsers) == 0
        assert pool._health_check_task is None or pool._health_check_task.cancelled()

    @pytest.mark.asyncio
    async def test_shutdown_not_initialized(self, settings):
        """Test shutting down a pool that was not initialized."""
        pool = BrowserPool(settings)

        # Should not raise an exception
        await pool.shutdown()

        assert pool._initialized is False

    @pytest.mark.asyncio
    async def test_shutdown_already_shutting_down(self, settings, mock_playwright):
        """Test shutting down when already in shutdown process."""
        pool = BrowserPool(settings)
        await pool.initialize()
        pool._shutting_down = True

        # Should not raise an exception
        await pool.shutdown()

        # Clean up
        pool._shutting_down = False

    def test_get_pool_stats(self, settings):
        """Test getting pool statistics."""
        pool = BrowserPool(settings)

        stats = pool.get_pool_stats()

        assert stats["pool_size"] == 2
        assert stats["total_browsers"] == 0
        assert stats["total_contexts"] == 0
        assert stats["max_contexts"] == 6  # 2 browsers * 3 contexts
        assert stats["initialized"] is False
        assert stats["shutting_down"] is False

    @pytest.mark.asyncio
    async def test_get_pool_stats_initialized(self, settings, mock_playwright):
        """Test getting pool statistics when initialized."""
        pool = BrowserPool(settings)
        await pool.initialize()

        stats = pool.get_pool_stats()

        assert stats["pool_size"] == 2
        assert stats["total_browsers"] == 2
        assert stats["total_contexts"] == 0
        assert stats["max_contexts"] == 6
        assert stats["initialized"] is True
        assert stats["shutting_down"] is False

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_multiple_contexts_from_same_browser(self, settings, mock_playwright):
        """Test that multiple contexts can be created from the same browser."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock contexts
        mock_context1 = AsyncMock()
        mock_context2 = AsyncMock()
        mock_context3 = AsyncMock()

        # Set up the browser to return different contexts
        contexts = [mock_context1, mock_context2, mock_context3]
        pool._browsers[0].browser.new_context = AsyncMock(side_effect=contexts)

        # Acquire multiple contexts
        async with pool.acquire_context() as context1:
            assert context1 == mock_context1
            assert pool._browsers[0].active_contexts == 1

            async with pool.acquire_context() as context2:
                assert context2 == mock_context2
                # Could be from same browser or different browser
                total_contexts = sum(b.active_contexts for b in pool._browsers)
                assert total_contexts == 2

        # All contexts should be released
        total_contexts = sum(b.active_contexts for b in pool._browsers)
        assert total_contexts == 0

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_semaphore_not_released_on_timeout(self, settings, mock_playwright):
        """Test that semaphore is not released if acquisition times out."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Manually acquire all semaphore permits to simulate high load
        max_permits = pool.pool_size * pool.max_contexts_per_browser
        for _ in range(max_permits):
            await pool._context_semaphore.acquire()

        # Now semaphore is at 0, any attempt to acquire should timeout
        initial_value = pool._context_semaphore._value
        assert initial_value == 0

        # Try to acquire with very short timeout - should timeout
        with pytest.raises(TimeoutError, match="Failed to acquire browser context"):
            async with pool.acquire_context(timeout=0.1):
                pass

        # Semaphore count should still be correct (not corrupted by failed acquisition)
        assert pool._context_semaphore._value == initial_value

        # Clean up - release the permits we manually acquired
        for _ in range(max_permits):
            pool._context_semaphore.release()

        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_immediate_context_return_when_available(self, settings, mock_playwright):
        """Test that context is returned immediately when pool has capacity."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context
        mock_context = AsyncMock()
        pool._browsers[0].browser.new_context = AsyncMock(return_value=mock_context)

        import time

        start_time = time.time()

        async with pool.acquire_context() as context:
            acquire_time = time.time() - start_time
            assert context == mock_context
            # Should be immediate (< 100ms)
            assert acquire_time < 0.1

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_context_queued_when_pool_full(self, settings, mock_playwright):
        """Test that requests are queued when pool is full."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock contexts
        contexts = [AsyncMock() for _ in range(10)]
        pool._browsers[0].browser.new_context = AsyncMock(side_effect=contexts)
        pool._browsers[1].browser.new_context = AsyncMock(side_effect=contexts)

        # Max contexts: 2 browsers * 3 contexts = 6
        # Acquire 6 contexts to fill the pool
        active_contexts = []

        async def hold_context():
            async with pool.acquire_context() as ctx:
                active_contexts.append(ctx)
                await asyncio.sleep(0.5)  # Hold for 500ms

        # Start 6 tasks to fill the pool
        fill_tasks = [asyncio.create_task(hold_context()) for _ in range(6)]

        # Give them time to acquire
        await asyncio.sleep(0.1)

        # Now pool should be full
        assert sum(b.active_contexts for b in pool._browsers) == 6

        # Try to acquire one more - should queue
        queued = False

        async def queued_acquire():
            nonlocal queued
            queued = True
            async with pool.acquire_context() as ctx:
                active_contexts.append(ctx)

        queued_task = asyncio.create_task(queued_acquire())

        # Give time for queue attempt
        await asyncio.sleep(0.1)

        # Task should be queued (not completed yet)
        assert not queued_task.done()
        assert queued

        # Wait for all to complete
        await asyncio.gather(*fill_tasks, queued_task)

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_fifo_queue_order(self, settings, mock_playwright):
        """Test that contexts are assigned in FIFO order."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock contexts
        contexts = [AsyncMock() for _ in range(10)]
        pool._browsers[0].browser.new_context = AsyncMock(side_effect=contexts)
        pool._browsers[1].browser.new_context = AsyncMock(side_effect=contexts)

        acquisition_order = []

        async def acquire_and_record(request_id: int):
            async with pool.acquire_context():
                acquisition_order.append(request_id)
                await asyncio.sleep(0.05)  # Hold briefly

        # Fill pool with first 6 requests
        tasks = [asyncio.create_task(acquire_and_record(i)) for i in range(6)]
        await asyncio.sleep(0.1)  # Let them acquire

        # Now add 3 more that will queue
        for i in range(6, 9):
            tasks.append(asyncio.create_task(acquire_and_record(i)))

        # Wait for all to complete
        await asyncio.gather(*tasks)

        # Check FIFO order: 0-5 acquired first (any order), then 6-8 in order
        assert len(acquisition_order) == 9
        # First 6 should be 0-5 in some order
        assert set(acquisition_order[:6]) == {0, 1, 2, 3, 4, 5}
        # Last 3 should be 6, 7, 8 in FIFO order
        assert acquisition_order[6:] == [6, 7, 8]

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_context_assigned_when_freed(self, settings, mock_playwright):
        """Test that queued requests get contexts when they're freed."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock contexts
        contexts = [AsyncMock() for _ in range(10)]
        pool._browsers[0].browser.new_context = AsyncMock(side_effect=contexts)
        pool._browsers[1].browser.new_context = AsyncMock(side_effect=contexts)

        # Fill the pool
        holders = []

        async def hold_context(duration: float):
            async with pool.acquire_context() as ctx:
                holders.append(ctx)
                await asyncio.sleep(duration)

        # Start 6 tasks that hold contexts
        hold_tasks = [asyncio.create_task(hold_context(0.3)) for _ in range(6)]
        await asyncio.sleep(0.1)  # Let them acquire

        # Verify pool is full
        assert sum(b.active_contexts for b in pool._browsers) == 6

        # Queue a request
        queued_acquired = False

        async def queued_request():
            nonlocal queued_acquired
            async with pool.acquire_context():
                queued_acquired = True

        queued_task = asyncio.create_task(queued_request())
        await asyncio.sleep(0.1)

        # Not acquired yet
        assert not queued_acquired

        # Wait for one holder to finish (after 0.3s total)
        await asyncio.sleep(0.3)

        # Now queued request should have acquired
        await asyncio.wait_for(queued_task, timeout=1.0)
        assert queued_acquired

        # Wait for all to complete
        await asyncio.gather(*hold_tasks)

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_queue_timeout(self, settings, mock_playwright):
        """Test that queue wait respects timeout."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock contexts
        contexts = [AsyncMock() for _ in range(10)]
        pool._browsers[0].browser.new_context = AsyncMock(side_effect=contexts)
        pool._browsers[1].browser.new_context = AsyncMock(side_effect=contexts)

        # Fill the pool and hold
        async def hold_forever():
            async with pool.acquire_context():
                await asyncio.sleep(10)  # Hold for long time

        # Start 6 tasks to fill pool
        hold_tasks = [asyncio.create_task(hold_forever()) for _ in range(6)]
        await asyncio.sleep(0.1)  # Let them acquire

        # Verify pool is full
        assert sum(b.active_contexts for b in pool._browsers) == 6

        # Try to acquire with short timeout - should fail
        with pytest.raises(TimeoutError, match="Failed to acquire browser context within"):
            async with pool.acquire_context(timeout=0.2):
                pass

        # Cancel the holders
        for task in hold_tasks:
            task.cancel()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_queue_metrics_tracking(self, settings, mock_playwright):
        """Test that queue metrics are properly tracked."""
        from crawler.core.metrics import browser_pool_queue_size

        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock contexts
        contexts = [AsyncMock() for _ in range(10)]
        pool._browsers[0].browser.new_context = AsyncMock(side_effect=contexts)
        pool._browsers[1].browser.new_context = AsyncMock(side_effect=contexts)

        # Initial queue size should be 0
        initial_queue_size = browser_pool_queue_size._value._value

        # Fill the pool
        async def hold_context():
            async with pool.acquire_context():
                await asyncio.sleep(0.3)

        # Start 6 tasks to fill pool
        hold_tasks = [asyncio.create_task(hold_context()) for _ in range(6)]
        await asyncio.sleep(0.1)

        # Add 2 more that will queue
        queued_tasks = [asyncio.create_task(hold_context()) for _ in range(2)]
        await asyncio.sleep(0.1)

        # Queue size should have increased (by 2)
        current_queue_size = browser_pool_queue_size._value._value
        assert current_queue_size == initial_queue_size + 2

        # Wait for all to complete
        await asyncio.gather(*hold_tasks, *queued_tasks)

        # Queue should be back to 0
        final_queue_size = browser_pool_queue_size._value._value
        assert final_queue_size == initial_queue_size

        # Clean up
        await pool.shutdown()


class TestBrowserContextCleanup:
    """Tests for browser context cleanup functionality."""

    @pytest.mark.asyncio
    async def test_cleanup_clears_cookies(self, settings, mock_playwright):
        """Test that cleanup clears cookies."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context with clear_cookies
        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock()
        mock_context.pages = []

        await pool._cleanup_context(mock_context)

        # Verify cookies were cleared
        mock_context.clear_cookies.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_clears_storage(self, settings, mock_playwright):
        """Test that cleanup clears localStorage and sessionStorage."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context with pages
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock()
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.new_page = AsyncMock()

        await pool._cleanup_context(mock_context)

        # Verify storage was cleared via evaluate
        mock_page.evaluate.assert_called_once()
        call_args = mock_page.evaluate.call_args[0][0]
        assert "localStorage.clear()" in call_args
        assert "sessionStorage.clear()" in call_args

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_closes_all_pages(self, settings, mock_playwright):
        """Test that cleanup closes all open pages."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context with multiple pages
        mock_pages = [AsyncMock() for _ in range(3)]
        for page in mock_pages:
            page.evaluate = AsyncMock()
            page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock()
        mock_context.pages = mock_pages
        mock_context.new_page = AsyncMock()

        await pool._cleanup_context(mock_context)

        # Verify all pages were closed
        for page in mock_pages:
            page.close.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_resets_to_blank_page(self, settings, mock_playwright):
        """Test that cleanup creates a clean about:blank page."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context with no pages after cleanup
        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock()
        mock_context.pages = []
        mock_context.new_page = AsyncMock()

        await pool._cleanup_context(mock_context)

        # Verify new blank page was created
        mock_context.new_page.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_handles_cookie_clear_error(self, settings, mock_playwright):
        """Test that cleanup continues even if cookie clearing fails."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context with clear_cookies that raises error
        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock(side_effect=Exception("Cookie error"))
        mock_context.pages = []
        mock_context.new_page = AsyncMock()

        # Should not raise exception
        await pool._cleanup_context(mock_context)

        # Verify new page was still created despite error
        mock_context.new_page.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_handles_storage_clear_error(self, settings, mock_playwright):
        """Test that cleanup continues even if storage clearing fails."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock page that raises error on evaluate
        mock_page = AsyncMock()
        mock_page.evaluate = AsyncMock(side_effect=Exception("Storage error"))
        mock_page.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock()
        mock_context.pages = [mock_page]
        mock_context.new_page = AsyncMock()

        # Should not raise exception
        await pool._cleanup_context(mock_context)

        # Verify page was still closed despite error
        mock_page.close.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_handles_page_close_error(self, settings, mock_playwright):
        """Test that cleanup continues even if page closing fails."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock pages where one fails to close
        mock_page1 = AsyncMock()
        mock_page1.evaluate = AsyncMock()
        mock_page1.close = AsyncMock(side_effect=Exception("Close error"))

        mock_page2 = AsyncMock()
        mock_page2.evaluate = AsyncMock()
        mock_page2.close = AsyncMock()

        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock()
        mock_context.pages = [mock_page1, mock_page2]
        mock_context.new_page = AsyncMock()

        # Should not raise exception
        await pool._cleanup_context(mock_context)

        # Verify both pages attempted close
        mock_page1.close.assert_called_once()
        mock_page2.close.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_cleanup_called_on_context_release(self, settings, mock_playwright):
        """Test that cleanup is called when context is released."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock context
        mock_context = AsyncMock()
        mock_context.clear_cookies = AsyncMock()
        mock_context.pages = []
        mock_context.new_page = AsyncMock()
        mock_context.close = AsyncMock()

        pool._browsers[0].browser.new_context = AsyncMock(return_value=mock_context)

        # Use context
        async with pool.acquire_context():
            pass

        # Verify cleanup was called
        mock_context.clear_cookies.assert_called_once()
        mock_context.close.assert_called_once()

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_initialization_failure_stops_playwright(self, settings):
        """Test that Playwright is stopped if initialization fails."""
        with patch("crawler.services.browser_pool.async_playwright") as mock_pw:
            playwright_instance = AsyncMock()
            mock_pw.return_value.start = AsyncMock(return_value=playwright_instance)

            # Make browser launch fail
            playwright_instance.chromium.launch = AsyncMock(side_effect=Exception("Launch failed"))
            playwright_instance.stop = AsyncMock()

            pool = BrowserPool(settings)

            # Initialization should fail
            with pytest.raises(RuntimeError, match="Failed to initialize browser pool"):
                await pool.initialize()

            # Verify playwright was stopped
            playwright_instance.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_context_creation_failure_does_not_decrement_counter(
        self, settings, mock_playwright
    ):
        """Test that active_contexts is not decremented if context creation fails."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Mock browser that fails to create context
        pool._browsers[0].browser.new_context = AsyncMock(
            side_effect=Exception("Context creation failed")
        )

        # Record initial active_contexts
        initial_active_contexts = pool._browsers[0].active_contexts

        # Try to acquire context - should fail
        with pytest.raises(Exception, match="Context creation failed"):
            async with pool.acquire_context():
                pass

        # Verify active_contexts was not decremented (should still be initial value)
        assert pool._browsers[0].active_contexts == initial_active_contexts

        # Verify it didn't go negative
        assert pool._browsers[0].active_contexts >= 0

        # Clean up
        await pool.shutdown()


class TestBrowserCrashDetection:
    """Tests for browser crash detection and recovery."""

    @pytest.mark.asyncio
    async def test_check_browser_health_returns_crash_status_when_not_connected(
        self, settings, mock_playwright
    ):
        """Test that health check returns crash status when browser is not connected."""
        pool = BrowserPool(settings)
        await pool.initialize()

        browser_instance = pool._browsers[0]
        browser_instance.browser.is_connected = MagicMock(return_value=False)

        is_healthy, is_crashed = await pool._check_browser_health(browser_instance)

        assert is_healthy is False
        assert is_crashed is True

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_check_browser_health_returns_crash_status_on_connection_error(
        self, settings, mock_playwright
    ):
        """Test that health check detects crashes from connection errors."""
        pool = BrowserPool(settings)
        await pool.initialize()

        browser_instance = pool._browsers[0]
        browser_instance.browser.is_connected = MagicMock(
            side_effect=Exception("Connection closed unexpectedly")
        )

        is_healthy, is_crashed = await pool._check_browser_health(browser_instance)

        assert is_healthy is False
        assert is_crashed is True

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_check_browser_health_returns_no_crash_on_transient_error(
        self, settings, mock_playwright
    ):
        """Test that health check doesn't flag transient errors as crashes."""
        pool = BrowserPool(settings)
        await pool.initialize()

        browser_instance = pool._browsers[0]
        browser_instance.browser.is_connected = MagicMock(
            side_effect=Exception("Timeout waiting for response")
        )

        is_healthy, is_crashed = await pool._check_browser_health(browser_instance)

        assert is_healthy is False
        assert is_crashed is False  # Not a crash, just a transient error

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_remove_and_replace_browser_success(self, settings, mock_playwright):
        """Test successful browser crash recovery."""
        pool = BrowserPool(settings)
        await pool.initialize()

        # Get initial browser count
        initial_count = len(pool._browsers)
        crashed_instance = pool._browsers[0]

        # Mock new browser for replacement
        new_browser = AsyncMock()
        new_browser.is_connected = MagicMock(return_value=True)
        mock_playwright.chromium.launch = AsyncMock(return_value=new_browser)

        # Remove and replace crashed browser
        async with pool._lock:
            await pool._remove_and_replace_browser(crashed_instance)

        # Verify browser was replaced
        assert len(pool._browsers) == initial_count
        assert crashed_instance not in pool._browsers

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_remove_and_replace_browser_failure(self, settings, mock_playwright):
        """Test browser crash recovery failure."""
        pool = BrowserPool(settings)
        await pool.initialize()

        crashed_instance = pool._browsers[0]

        # Mock launch failure
        mock_playwright.chromium.launch = AsyncMock(
            side_effect=Exception("Failed to launch browser")
        )

        # Attempt to replace crashed browser should raise BrowserCrashError
        async with pool._lock:
            with pytest.raises(BrowserCrashError, match="Failed to recover from browser crash"):
                await pool._remove_and_replace_browser(crashed_instance)

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_health_check_detects_and_recovers_from_crash(self, settings):
        """Test that health check automatically recovers from browser crashes."""
        with patch("crawler.services.browser_pool.async_playwright") as mock_pw:
            playwright_instance = AsyncMock()
            mock_pw.return_value.start = AsyncMock(return_value=playwright_instance)

            # Create two distinct browser mocks
            browser1 = AsyncMock()
            browser2 = AsyncMock()

            # Browser 1 will be healthy initially, then crash
            browser1.is_connected = MagicMock(return_value=True)
            browser1.new_context = AsyncMock()
            browser1.close = AsyncMock()

            # Browser 2 stays healthy
            browser2.is_connected = MagicMock(return_value=True)
            browser2.new_context = AsyncMock()
            browser2.close = AsyncMock()

            # Setup playwright to return different browsers
            playwright_instance.chromium.launch = AsyncMock(side_effect=[browser1, browser2])
            playwright_instance.stop = AsyncMock()

            pool = BrowserPool(settings)
            await pool.initialize()

            # Now simulate browser1 crash - override its is_connected to return False
            browser1.is_connected = MagicMock(return_value=False)

            # Store reference to crashed browser
            crashed_browser = pool._browsers[0]

            # Mock replacement browser
            replacement_browser = AsyncMock()
            replacement_browser.is_connected = MagicMock(return_value=True)
            replacement_browser.new_context = AsyncMock()
            playwright_instance.chromium.launch = AsyncMock(return_value=replacement_browser)

            # Run health check
            result = await pool.health_check()

            # Verify crashed browser was replaced
            assert crashed_browser not in pool._browsers
            assert len(pool._browsers) == 2
            # One healthy browser (browser2) plus potentially the replacement
            # (replacement health will be checked in next cycle)
            assert result["healthy_browsers"] >= 1

            # Clean up
            await pool.shutdown()

    @pytest.mark.asyncio
    async def test_acquire_context_detects_crash_during_creation(self, settings, mock_playwright):
        """Test that context acquisition detects browser crashes."""
        pool = BrowserPool(settings)
        await pool.initialize()

        crashed_browser = pool._browsers[0]

        # Mock browser crash during context creation
        crashed_browser.browser.new_context = AsyncMock(
            side_effect=Exception("Browser connection closed")
        )

        # Mock successful browser launch for replacement
        new_browser = AsyncMock()
        new_browser.is_connected = MagicMock(return_value=True)
        mock_playwright.chromium.launch = AsyncMock(return_value=new_browser)

        # Try to acquire context - should detect crash and attempt recovery
        with pytest.raises(BrowserCrashError, match="Browser crashed during context creation"):
            async with pool.acquire_context():
                pass

        # Verify crashed browser was replaced
        assert crashed_browser not in pool._browsers

        # Clean up
        await pool.shutdown()

    @pytest.mark.asyncio
    async def test_crash_metrics_incremented(self, settings, mock_playwright):
        """Test that crash metrics are properly incremented."""
        from crawler.core.metrics import browser_crash_recoveries_total, browser_crashes_total

        pool = BrowserPool(settings)
        await pool.initialize()

        # Record initial metric values
        initial_crashes = browser_crashes_total.labels(browser_type="chromium")._value._value
        initial_recoveries = browser_crash_recoveries_total._value._value

        crashed_browser = pool._browsers[0]

        # Mock successful browser launch for replacement
        new_browser = AsyncMock()
        new_browser.is_connected = MagicMock(return_value=True)
        mock_playwright.chromium.launch = AsyncMock(return_value=new_browser)

        # Trigger crash recovery
        async with pool._lock:
            await pool._remove_and_replace_browser(crashed_browser)

        # Verify metrics were incremented
        current_crashes = browser_crashes_total.labels(browser_type="chromium")._value._value
        current_recoveries = browser_crash_recoveries_total._value._value

        assert current_crashes == initial_crashes + 1
        assert current_recoveries == initial_recoveries + 1

        # Clean up
        await pool.shutdown()
