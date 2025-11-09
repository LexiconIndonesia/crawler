"""Browser step executor for Playwright and undetected-chromedriver.

Handles browser automation for JavaScript-heavy pages.
"""

from __future__ import annotations

from typing import Any

from crawler.core.logging import get_logger
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors.base import BaseStepExecutor, ExecutionResult

logger = get_logger(__name__)


class BrowserExecutor(BaseStepExecutor):
    """Executor for Browser method steps using Playwright or undetected-chrome.

    Note: This is a simplified implementation. In production, you would:
    1. Use a browser pool for efficiency
    2. Handle browser-specific options (headless, user agent, etc.)
    3. Implement anti-detection measures for undetected-chrome
    4. Add screenshot and HAR capture capabilities
    """

    def __init__(
        self,
        selector_processor: SelectorProcessor | None = None,
    ):
        """Initialize browser executor.

        Args:
            selector_processor: Selector processor for data extraction
        """
        self.selector_processor = selector_processor or SelectorProcessor()
        self._browser = None
        self._context = None

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
            wait_for = step_config.get("wait_for", "load")  # load, domcontentloaded, networkidle
            selector_wait = step_config.get("selector_wait")
            browser_type = step_config.get("browser_type", "chromium")

            logger.info(
                "browser_request_starting",
                url=url,
                browser_type=browser_type,
                timeout=timeout,
            )

            # Launch browser
            async with async_playwright() as p:
                # Select browser type
                if browser_type == "firefox":
                    browser = await p.firefox.launch()
                elif browser_type == "webkit":
                    browser = await p.webkit.launch()
                else:
                    browser = await p.chromium.launch()

                # Create context and page
                context = await browser.new_context()
                page = await context.new_page()

                try:
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
                    await page.close()
                    await context.close()
                    await browser.close()

        except Exception as e:
            return self._create_error_result(
                f"Browser execution error: {e}",
                url=url,
            )

    async def cleanup(self) -> None:
        """Clean up browser resources.

        Note: Browser is launched and closed per request in this implementation.
        In production, you would use a browser pool and close it here.
        """
        logger.debug("browser_executor_cleanup_called")
        # No persistent resources to clean up in this implementation
