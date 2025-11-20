"""Scrape step executor for extracting content from detail pages.

This executor handles scrape steps that extract content from multiple URLs.
It processes URLs in batches for efficiency and handles partial failures gracefully.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from crawler.core.logging import get_logger
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors.base import BaseStepExecutor, ExecutionResult

if TYPE_CHECKING:
    from crawler.services.step_executors import APIExecutor, BrowserExecutor, HTTPExecutor

logger = get_logger(__name__)


class ScrapeExecutor(BaseStepExecutor):
    """Executor for scrape steps that extract content from detail pages.

    This executor:
    1. Accepts URLs from previous steps
    2. Processes URLs in batches of 100 for efficiency
    3. Extracts content using configured selectors
    4. Handles partial failures (continues with successful extractions)
    5. Returns structured extracted data and documents

    Example:
        >>> executor = ScrapeExecutor(
        ...     http_executor=http_executor,
        ...     selector_processor=selector_processor,
        ... )
        >>> result = await executor.execute(
        ...     url="https://example.com/article/123",
        ...     step_config={"method": "http"},
        ...     selectors={"title": "h1", "content": ".article-body"},
        ... )
        >>> print(result.extracted_data)  # {"title": "...", "content": "..."}
    """

    # Default batch size for processing URLs
    DEFAULT_BATCH_SIZE = 100

    def __init__(
        self,
        http_executor: HTTPExecutor,
        api_executor: APIExecutor,
        browser_executor: BrowserExecutor,
        selector_processor: SelectorProcessor | None = None,
        batch_size: int | None = None,
    ):
        """Initialize scrape executor.

        Args:
            http_executor: HTTP executor for HTTP method
            api_executor: API executor for API method
            browser_executor: Browser executor for browser method
            selector_processor: Selector processor for data extraction
            batch_size: Number of URLs to process in each batch (default: 100)
        """
        self.http_executor = http_executor
        self.api_executor = api_executor
        self.browser_executor = browser_executor
        self.selector_processor = selector_processor or SelectorProcessor()
        self.batch_size = batch_size or self.DEFAULT_BATCH_SIZE

    async def execute(
        self,
        url: str | list[str],
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute scrape step to extract content from URLs.

        Args:
            url: Single URL or list of URLs to scrape
            step_config: Configuration (method, timeout, headers, etc.)
            selectors: Selectors for content extraction

        Returns:
            ExecutionResult with extracted content and metadata

        For single URL:
        - extracted_data: {"title": "...", "content": "..."}

        For multiple URLs:
        - extracted_data: {"items": [{"title": "...", "content": "..."}, ...]}
        """
        try:
            # Step 1: Normalize URL input to list
            urls = [url] if isinstance(url, str) else url
            total_urls = len(urls)

            # Guard: no URLs to process
            if total_urls == 0:
                logger.warning("scrape_no_urls", step_config=step_config)
                return self._create_success_result(
                    content="",
                    extracted_data={},
                    total_urls=0,
                    successful_urls=0,
                    failed_urls=0,
                )

            # Step 2: Get method-specific executor
            method = step_config.get("method", "http").lower()
            executor = self._get_method_executor(method)

            logger.info(
                "scrape_starting",
                total_urls=total_urls,
                batch_size=self.batch_size,
                method=method,
            )

            # Step 3: Process URLs in batches
            all_extracted_data: list[dict[str, Any]] = []
            failed_urls = 0
            errors: list[str] = []

            for batch_start in range(0, total_urls, self.batch_size):
                batch_end = min(batch_start + self.batch_size, total_urls)
                batch_urls = urls[batch_start:batch_end]
                batch_num = (batch_start // self.batch_size) + 1
                total_batches = (total_urls + self.batch_size - 1) // self.batch_size

                logger.info(
                    "scrape_batch_starting",
                    batch_num=batch_num,
                    total_batches=total_batches,
                    batch_size=len(batch_urls),
                )

                # Process all URLs in the batch concurrently using asyncio.gather
                tasks = [
                    executor.execute(batch_url, step_config, selectors) for batch_url in batch_urls
                ]

                # Execute all tasks concurrently
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results
                for idx, result_or_exception in enumerate(batch_results):
                    global_idx = batch_start + idx
                    batch_url = batch_urls[idx]

                    # Handle exceptions from gather
                    if isinstance(result_or_exception, Exception):
                        failed_urls += 1
                        error_msg = f"URL {global_idx} ({batch_url}): {result_or_exception}"
                        errors.append(error_msg)
                        logger.warning(
                            "url_scraped_failed",
                            url_index=global_idx,
                            url=batch_url,
                            error=str(result_or_exception),
                        )
                        continue

                    # Type narrowing: after exception check, must be ExecutionResult
                    assert isinstance(result_or_exception, ExecutionResult)
                    result = result_or_exception

                    if result.success:
                        # Include URL with extracted data for later persistence
                        page_data = {
                            "_url": batch_url,  # Store URL for database persistence
                            "_content": result.content,  # Store raw content if available
                            **result.extracted_data,  # Merge extracted fields
                        }
                        all_extracted_data.append(page_data)
                        logger.debug(
                            "url_scraped_success",
                            url_index=global_idx,
                            url=batch_url,
                            fields=len(result.extracted_data),
                        )
                    else:
                        failed_urls += 1
                        error_msg = f"URL {global_idx} ({batch_url}): {result.error}"
                        errors.append(error_msg)
                        logger.warning(
                            "url_scraped_failed",
                            url_index=global_idx,
                            url=batch_url,
                            error=result.error,
                        )

                # Count successes directly from batch results
                successful_in_batch = sum(
                    1 for r in batch_results if isinstance(r, ExecutionResult) and r.success
                )
                logger.info(
                    "scrape_batch_completed",
                    batch_num=batch_num,
                    successful_in_batch=successful_in_batch,
                    failed_in_batch=len(batch_urls) - successful_in_batch,
                )

            # Step 4: Calculate results
            successful_urls = len(all_extracted_data)

            # Step 5: Check for complete failure
            if successful_urls == 0:
                error_summary = "; ".join(errors[:5])  # Limit error message size
                if len(errors) > 5:
                    error_summary += f"... and {len(errors) - 5} more errors"

                logger.error(
                    "scrape_failed_all_urls",
                    total_urls=total_urls,
                    failed_urls=failed_urls,
                )
                return self._create_error_result(
                    f"All URLs failed: {error_summary}",
                    total_urls=total_urls,
                    failed_urls=failed_urls,
                )

            # Step 6: Structure output based on URL count
            if len(urls) == 1:
                # Single URL: return extracted data directly
                extracted_data = all_extracted_data[0] if all_extracted_data else {}
            else:
                # Multiple URLs: return as items array
                extracted_data = {"items": all_extracted_data}

            # Step 7: Log completion
            logger.info(
                "scrape_completed",
                total_urls=total_urls,
                successful_urls=successful_urls,
                failed_urls=failed_urls,
                batches_processed=total_batches,
            )

            # Return success result with metadata
            return self._create_success_result(
                content="",  # Don't store raw content for scrape steps
                extracted_data=extracted_data,
                total_urls=total_urls,
                successful_urls=successful_urls,
                failed_urls=failed_urls,
                errors=errors if errors else None,
            )

        except Exception as e:
            logger.error(
                "scrape_execution_error",
                error=str(e),
                exc_info=True,
            )
            return self._create_error_result(
                f"Scrape execution error: {e}",
            )

    def _get_method_executor(self, method: str) -> HTTPExecutor | APIExecutor | BrowserExecutor:
        """Get executor for specified method.

        Args:
            method: Method type (http, api, browser)

        Returns:
            Appropriate executor instance

        Raises:
            ValueError: If method is not supported
        """
        if method == "http":
            return self.http_executor
        elif method == "api":
            return self.api_executor
        elif method == "browser":
            return self.browser_executor
        else:
            raise ValueError(f"Unsupported method: {method}")

    async def cleanup(self) -> None:
        """Clean up resources.

        Note: This executor reuses existing executors, so cleanup is delegated
        to the parent orchestrator which owns the executor instances.
        """
        # Executors are owned by StepOrchestrator, which handles cleanup
        logger.debug("scrape_executor_cleanup_complete")
