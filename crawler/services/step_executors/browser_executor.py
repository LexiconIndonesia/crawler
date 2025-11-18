"""Browser step executor for Playwright and undetected-chromedriver.

Handles browser automation for JavaScript-heavy pages.
"""

from __future__ import annotations

from typing import Any

from crawler.core.logging import get_logger
from crawler.services.browser_pool import BrowserPool
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors.base import BaseStepExecutor, ExecutionResult

logger = get_logger(__name__)


class BrowserExecutor(BaseStepExecutor):
    """Executor for Browser method steps using Playwright or undetected-chrome.

    Supports two modes:
    1. Browser pool mode (recommended): Uses a shared browser pool for efficiency
    2. Per-request mode (fallback): Launches a new browser for each request

    The executor automatically uses the pool if available, falling back to
    per-request browsers if the pool is not initialized.
    """

    def __init__(
        self,
        selector_processor: SelectorProcessor | None = None,
        browser_pool: BrowserPool | None = None,
    ):
        """Initialize browser executor.

        Args:
            selector_processor: Selector processor for data extraction
            browser_pool: Optional browser pool for efficient browser reuse
        """
        self.selector_processor = selector_processor or SelectorProcessor()
        self.browser_pool = browser_pool

    async def execute(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute browser navigation and extract data.

        Args:
            url: Target URL
            step_config: Configuration (timeout, wait_for, browser_type, etc.)
            selectors: Selectors for data extraction

        Returns:
            ExecutionResult with page content and extracted data
        """
        # Guard: check if browser pool is available and initialized
        if self.browser_pool is not None and self.browser_pool._initialized:
            return await self._execute_with_pool(url, step_config, selectors)
        else:
            return await self._execute_per_request(url, step_config, selectors)

    async def _execute_with_pool(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute using browser pool (recommended).

        Args:
            url: Target URL
            step_config: Configuration (timeout, wait_for, browser_type, etc.)
            selectors: Selectors for data extraction

        Returns:
            ExecutionResult with page content and extracted data
        """
        try:
            # Extract config
            timeout = step_config.get("timeout", 30) * 1000  # Convert to milliseconds
            # Backward compatibility: support old "wait_for" key, fallback to "wait_until"
            wait_for = step_config.get("wait_for") or step_config.get("wait_until", "load")
            selector_wait = step_config.get("selector_wait")

            logger.info(
                "browser_request_starting_with_pool",
                url=url,
                timeout=timeout,
            )

            # Acquire context from pool
            # Type narrowing: we know browser_pool is not None because this method
            # is only called when browser_pool is not None and initialized
            assert self.browser_pool is not None
            async with self.browser_pool.acquire_context() as context:
                page = None
                try:
                    # Create page
                    page = await context.new_page()

                    # Navigate to URL
                    response = await page.goto(url, timeout=timeout, wait_until=wait_for)

                    # Check response status
                    status_code = response.status if response else None
                    if status_code and not 200 <= status_code < 300:
                        return self._create_error_result(
                            f"HTTP {status_code} error",
                            url=url,
                            status_code=status_code,
                        )

                    # Wait for specific selector if configured
                    if selector_wait:
                        try:
                            await page.wait_for_selector(
                                selector_wait,
                                timeout=step_config.get("selector_wait_timeout", 10) * 1000,
                            )
                        except Exception as e:
                            logger.warning(
                                "selector_wait_timeout",
                                url=url,
                                selector=selector_wait,
                                error=str(e),
                            )

                    # Get page content
                    content = await page.content()

                    # Extract data using selectors
                    extracted_data = {}
                    if selectors:
                        extracted_data = self.selector_processor.process_selectors(
                            content, selectors
                        )

                    logger.info(
                        "browser_request_completed_with_pool",
                        url=url,
                        status_code=status_code,
                        content_length=len(content),
                        extracted_fields=len(extracted_data),
                    )

                    return self._create_success_result(
                        content=content,
                        extracted_data=extracted_data,
                        status_code=status_code,
                        content_length=len(content),
                        final_url=page.url,
                    )

                finally:
                    # Guard cleanup: close page if it was created
                    if page is not None:
                        try:
                            await page.close()
                        except Exception as e:
                            logger.debug("page_close_error", error=str(e))

        except Exception as e:
            return self._create_error_result(
                f"Browser execution error: {e}",
                url=url,
            )

    async def _execute_per_request(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute by launching a new browser per request (fallback).

        Args:
            url: Target URL
            step_config: Configuration (timeout, wait_for, browser_type, etc.)
            selectors: Selectors for data extraction

        Returns:
            ExecutionResult with page content and extracted data
        """
        try:
            # Import playwright lazily (only when needed)
            try:
                from playwright.async_api import async_playwright
            except ImportError:
                return self._create_error_result(
                    "Playwright not installed. "
                    "Run: uv pip install playwright && playwright install",
                    url=url,
                )

            # Extract config
            timeout = step_config.get("timeout", 30) * 1000  # Convert to milliseconds
            # Backward compatibility: support old "wait_for" key, fallback to "wait_until"
            wait_for = step_config.get("wait_for") or step_config.get("wait_until", "load")
            selector_wait = step_config.get("selector_wait")
            browser_type = step_config.get("browser_type", "chromium")

            logger.info(
                "browser_request_starting_per_request",
                url=url,
                browser_type=browser_type,
                timeout=timeout,
            )

            # Launch browser
            async with async_playwright() as p:
                # Initialize resources to None to prevent UnboundLocalError in finally block
                browser = None
                context = None
                page = None

                try:
                    # Select browser type and configure launch args
                    if browser_type == "firefox":
                        # Firefox-specific args (minimal, Firefox doesn't support most Chrome flags)
                        browser = await p.firefox.launch()
                    elif browser_type == "webkit":
                        # WebKit-specific args (minimal, WebKit doesn't support Chrome flags)
                        browser = await p.webkit.launch()
                    else:
                        # Chromium-specific stealth args
                        # --disable-blink-features=AutomationControlled: Hide automation
                        # --no-sandbox: Allow running as root (SECURITY TRADEOFF: needed
                        #               for Docker containers but reduces process isolation.
                        #               Only use in trusted environments like containerized
                        #               crawlers, not production web apps)
                        args = ["--disable-blink-features=AutomationControlled", "--no-sandbox"]
                        browser = await p.chromium.launch(
                            args=args, ignore_default_args=["--enable-automation"]
                        )

                    # Create context with stealth and page
                    ua = (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    )
                    context = await browser.new_context(
                        user_agent=ua, viewport={"width": 1920, "height": 1080}
                    )
                    page = await context.new_page()

                    # Navigate to URL
                    response = await page.goto(url, timeout=timeout, wait_until=wait_for)

                    # Check response status
                    status_code = response.status if response else None
                    if status_code and not 200 <= status_code < 300:
                        return self._create_error_result(
                            f"HTTP {status_code} error",
                            url=url,
                            status_code=status_code,
                        )

                    # Wait for specific selector if configured
                    if selector_wait:
                        try:
                            await page.wait_for_selector(
                                selector_wait,
                                timeout=step_config.get("selector_wait_timeout", 10) * 1000,
                            )
                        except Exception as e:
                            logger.warning(
                                "selector_wait_timeout",
                                url=url,
                                selector=selector_wait,
                                error=str(e),
                            )

                    # Get page content
                    content = await page.content()

                    # Extract data using selectors
                    extracted_data = {}
                    if selectors:
                        extracted_data = self.selector_processor.process_selectors(
                            content, selectors
                        )

                    logger.info(
                        "browser_request_completed",
                        url=url,
                        status_code=status_code,
                        content_length=len(content),
                        extracted_fields=len(extracted_data),
                    )

                    return self._create_success_result(
                        content=content,
                        extracted_data=extracted_data,
                        status_code=status_code,
                        content_length=len(content),
                        final_url=page.url,
                    )

                finally:
                    # Guard cleanup: close each resource if it was created
                    # Wrap each close in try/except to prevent secondary errors from masking
                    # the original exception
                    if page is not None:
                        try:
                            await page.close()
                        except Exception as e:
                            logger.debug("page_close_error", error=str(e))

                    if context is not None:
                        try:
                            await context.close()
                        except Exception as e:
                            logger.debug("context_close_error", error=str(e))

                    if browser is not None:
                        try:
                            await browser.close()
                        except Exception as e:
                            logger.debug("browser_close_error", error=str(e))

        except Exception as e:
            return self._create_error_result(
                f"Browser execution error: {e}",
                url=url,
            )

    async def cleanup(self) -> None:
        """Clean up browser resources.

        Note: Browser pool cleanup is handled by the application lifespan manager.
        This method is for per-request cleanup only (currently nothing to clean).
        """
        logger.debug("browser_executor_cleanup_called")
        # Browser pool is managed at application level, not per-executor
        # Per-request browsers are cleaned up in finally blocks
