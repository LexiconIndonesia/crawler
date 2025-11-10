"""Crawl step executor for retrieving lists of URLs with pagination support.

This executor handles crawl steps that retrieve URLs from one or more pages.
It integrates pagination, URL extraction, and deduplication.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from crawler.api.generated import PaginationConfig
from crawler.core.logging import get_logger
from crawler.services.pagination import PaginationService
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors.base import BaseStepExecutor, ExecutionResult

if TYPE_CHECKING:
    from crawler.services.step_executors import APIExecutor, BrowserExecutor, HTTPExecutor

logger = get_logger(__name__)


class CrawlExecutor(BaseStepExecutor):
    """Executor for crawl steps that retrieve URLs from pages.

    This executor:
    1. Generates pagination URLs (if pagination is enabled)
    2. Fetches each page using the appropriate method (HTTP/API/Browser)
    3. Extracts URLs from each page using selectors
    4. Deduplicates and aggregates URLs
    5. Returns metadata about the crawl operation

    Example:
        >>> executor = CrawlExecutor(
        ...     http_executor=http_executor,
        ...     selector_processor=selector_processor,
        ... )
        >>> result = await executor.execute(
        ...     url="https://example.com/articles",
        ...     step_config={
        ...         "method": "http",
        ...         "pagination": {"enabled": True, "max_pages": 10},
        ...     },
        ...     selectors={"urls": {"selector": "a.article", "attribute": "href", "type": "array"}},
        ... )
        >>> print(result.extracted_data["urls"])  # List of extracted URLs
    """

    def __init__(
        self,
        http_executor: HTTPExecutor,
        api_executor: APIExecutor,
        browser_executor: BrowserExecutor,
        selector_processor: SelectorProcessor | None = None,
        pagination_service: PaginationService | None = None,
    ):
        """Initialize crawl executor.

        Args:
            http_executor: HTTP executor for HTTP method
            api_executor: API executor for API method
            browser_executor: Browser executor for browser method
            selector_processor: Selector processor for data extraction
            pagination_service: Pagination service for URL generation
        """
        self.http_executor = http_executor
        self.api_executor = api_executor
        self.browser_executor = browser_executor
        self.selector_processor = selector_processor or SelectorProcessor()
        self.pagination_service = pagination_service or PaginationService()

    async def execute(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute crawl step to retrieve URLs.

        Args:
            url: Seed URL to start crawling from
            step_config: Configuration (method, pagination, timeout, etc.)
            selectors: Selectors for URL extraction (typically targets anchor tags)

        Returns:
            ExecutionResult with extracted URLs and metadata

        The extracted_data will contain:
        - urls: List of extracted URLs (deduplicated)
        - total_urls: Total number of URLs found
        - pages_crawled: Number of pages successfully crawled
        - pages_failed: Number of pages that failed
        """
        try:
            # Step 1: Get method-specific executor
            method = step_config.get("method", "http").lower()
            executor = self._get_method_executor(method)

            # Step 2: Generate pagination URLs
            pagination_urls = self._generate_pagination_urls(url, step_config)
            logger.info(
                "crawl_starting",
                seed_url=url,
                total_pages=len(pagination_urls),
                method=method,
            )

            # Step 3: Crawl each page and extract URLs
            all_urls: list[str] = []
            pages_crawled = 0
            pages_failed = 0
            errors: list[str] = []

            for idx, page_url in enumerate(pagination_urls):
                logger.debug(
                    "crawling_page",
                    page_index=idx,
                    total_pages=len(pagination_urls),
                    page_url=page_url,
                )

                # Execute page fetch
                page_result = await executor.execute(page_url, step_config, selectors)

                if page_result.success:
                    pages_crawled += 1

                    # Extract URLs from page
                    page_urls = self._extract_urls_from_result(page_result)
                    all_urls.extend(page_urls)

                    logger.debug(
                        "page_crawled",
                        page_index=idx,
                        page_url=page_url,
                        urls_found=len(page_urls),
                    )
                else:
                    pages_failed += 1
                    error_msg = f"Page {idx} ({page_url}): {page_result.error}"
                    errors.append(error_msg)
                    logger.warning(
                        "page_crawl_failed",
                        page_index=idx,
                        page_url=page_url,
                        error=page_result.error,
                    )

            # Step 4: Deduplicate URLs
            unique_urls = list(dict.fromkeys(all_urls))  # Preserve order while deduplicating

            # Step 5: Build extracted_data with selector field names AND crawl metadata
            # We need to preserve the original selector field names for data passing
            extracted_data: dict[str, Any] = {}

            # If selectors were specified, collect the last page's extracted data
            # to preserve field names (e.g., "article_urls" instead of "urls")
            if selectors and pages_crawled > 0:
                # Reconstruct the extracted data with original field names
                # For crawl steps, we typically have one main field with URLs
                for field_name in selectors.keys():
                    extracted_data[field_name] = unique_urls

            # Always add standard crawl metadata fields
            extracted_data["_crawl_metadata"] = {
                "total_urls": len(unique_urls),
                "pages_crawled": pages_crawled,
                "pages_failed": pages_failed,
                "duplicate_urls": len(all_urls) - len(unique_urls),
            }

            # Step 6: Check if ALL pages failed (complete failure)
            if pages_crawled == 0 and pages_failed > 0:
                error_summary = "; ".join(errors) if errors else "All pages failed"
                logger.error(
                    "crawl_failed_all_pages",
                    seed_url=url,
                    pages_failed=pages_failed,
                )
                return self._create_error_result(
                    f"All pages failed: {error_summary}",
                    seed_url=url,
                    pages_failed=pages_failed,
                )

            # Step 7: Handle 0 URLs found (not an error if pages were crawled successfully)
            if len(unique_urls) == 0:
                logger.info(
                    "crawl_completed_no_urls",
                    seed_url=url,
                    pages_crawled=pages_crawled,
                    pages_failed=pages_failed,
                )

            logger.info(
                "crawl_completed",
                seed_url=url,
                total_urls=len(unique_urls),
                duplicate_urls=len(all_urls) - len(unique_urls),
                pages_crawled=pages_crawled,
                pages_failed=pages_failed,
            )

            # Return result with extracted URLs and metadata
            return self._create_success_result(
                content="",  # Don't store raw HTML content for crawl steps
                extracted_data=extracted_data,
                seed_url=url,
                pagination_enabled=step_config.get("pagination", {}).get("enabled", False),
                total_pages=len(pagination_urls),
                duplicate_urls=len(all_urls) - len(unique_urls),
                errors=errors if errors else None,
            )

        except Exception as e:
            logger.error(
                "crawl_execution_error",
                seed_url=url,
                error=str(e),
                exc_info=True,
            )
            return self._create_error_result(
                f"Crawl execution error: {e}",
                seed_url=url,
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

    def _generate_pagination_urls(self, seed_url: str, step_config: dict[str, Any]) -> list[str]:
        """Generate pagination URLs from seed URL and config.

        Args:
            seed_url: Starting URL
            step_config: Step configuration with pagination settings

        Returns:
            List of URLs to crawl (includes seed URL if pagination disabled)
        """
        # Guard: no pagination config
        pagination_dict = step_config.get("pagination")
        if not pagination_dict:
            return [seed_url]

        # Guard: pagination explicitly disabled
        if not pagination_dict.get("enabled", False):
            return [seed_url]

        # Convert dict to PaginationConfig
        try:
            pagination_config = PaginationConfig(**pagination_dict)
            urls = self.pagination_service.generate_pagination_urls(seed_url, pagination_config)
            return urls
        except Exception as e:
            logger.error(
                "pagination_generation_error",
                seed_url=seed_url,
                error=str(e),
            )
            # Fallback to seed URL only
            return [seed_url]

    def _extract_urls_from_result(self, result: ExecutionResult) -> list[str]:
        """Extract URLs from execution result.

        Args:
            result: Execution result from page fetch

        Returns:
            List of URLs extracted from result

        This method extracts ALL string and list values from the result,
        as any field could contain URLs for crawling purposes.
        """
        # Guard: no extracted data
        if not result.extracted_data:
            return []

        urls: list[str] = []

        # Extract from ALL fields (any field could contain URLs)
        for field_name, value in result.extracted_data.items():
            # Handle list of URLs
            if isinstance(value, list):
                # Filter out non-string values
                urls.extend([str(u) for u in value if u and isinstance(u, str)])
            # Handle single URL string
            elif isinstance(value, str):
                urls.append(value)

        return urls

    async def cleanup(self) -> None:
        """Clean up resources.

        Note: This executor reuses existing executors, so cleanup is delegated
        to the parent orchestrator which owns the executor instances.
        """
        # Executors are owned by StepOrchestrator, which handles cleanup
        logger.debug("crawl_executor_cleanup_complete")
