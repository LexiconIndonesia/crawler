"""Pagination service for intelligent page crawling.

This service orchestrates pagination detection and URL generation for crawl jobs.
It integrates the pagination utilities with the crawl configuration system.
"""

from collections.abc import AsyncIterator, Awaitable, Callable

from crawler.api.generated import PaginationConfig
from crawler.core.logging import get_logger
from crawler.utils.pagination import (
    PaginationPatternDetector,
    PaginationStopDetector,
    PaginationURLGenerator,
    StopCondition,
    TemplatePattern,
)

logger = get_logger(__name__)


class PaginationService:
    """Service for handling pagination in crawl jobs.

    This service provides:
    - Automatic pagination pattern detection from seed URLs
    - URL generation for detected patterns
    - Stop condition detection (404, duplicates, empty pages)
    - Integration with PaginationConfig from crawl steps

    Example:
        >>> config = PaginationConfig(enabled=True, max_pages=50)
        >>> service = PaginationService()
        >>> urls = service.generate_pagination_urls(
        ...     seed_url="https://example.com/products?page=5",
        ...     config=config
        ... )
    """

    # Default values for pagination configuration
    DEFAULT_MAX_PAGES = 100
    DEFAULT_START_PAGE = 1
    DEFAULT_MIN_CONTENT_LENGTH = 100
    DEFAULT_MAX_EMPTY_RESPONSES = 2

    def __init__(self) -> None:
        """Initialize pagination service."""
        self.detector = PaginationPatternDetector()

    def generate_pagination_urls(self, seed_url: str, config: PaginationConfig) -> list[str]:
        """Generate all pagination URLs from seed URL.

        This method:
        1. Detects pagination pattern from seed URL (if not configured)
        2. Uses url_template from config if provided
        3. Falls back to selector-based approach if no pattern detected
        4. Generates all URLs up to max_pages limit

        Args:
            seed_url: The seed URL to start pagination from
            config: Pagination configuration from crawl step

        Returns:
            List of pagination URLs to crawl

        Raises:
            ValueError: If pagination is disabled or invalid config
        """
        if not config.enabled:
            logger.debug("pagination_disabled", seed_url=seed_url)
            return [seed_url]

        max_pages = (
            config.max_pages if config.max_pages is not None else self.DEFAULT_MAX_PAGES
        )

        # Strategy 1: Use url_template if provided (explicit config)
        if config.url_template:
            logger.info(
                "using_template_pattern",
                seed_url=seed_url,
                template=config.url_template,
                max_pages=max_pages,
            )
            start_page = (
                config.start_page
                if config.start_page is not None
                else self.DEFAULT_START_PAGE
            )
            template_pattern = TemplatePattern(
                current_page=start_page,
                template=config.url_template,
            )
            generator = PaginationURLGenerator(seed_url, template_pattern, max_pages=max_pages)

            # Generate all URLs from template (including start page)
            # Template defines the URL structure, so we generate from start_page to max_pages
            urls = generator.generate_range(start_page, max_pages)
            logger.info(
                "pagination_urls_generated_from_template",
                seed_url=seed_url,
                total_urls=len(urls),
            )
            return urls

        # Strategy 2: Auto-detect pattern from seed URL
        detected_pattern = self.detector.detect(seed_url)
        if detected_pattern:
            logger.info(
                "pagination_pattern_detected",
                seed_url=seed_url,
                pattern_type=type(detected_pattern).__name__,
                current_page=detected_pattern.current_page,
                max_pages=max_pages,
            )
            generator = PaginationURLGenerator(seed_url, detected_pattern, max_pages=max_pages)
            # Include seed URL + all generated URLs
            remaining_urls = generator.generate_all()
            urls = [seed_url] + remaining_urls
            logger.info(
                "pagination_urls_generated_from_detection",
                seed_url=seed_url,
                total_urls=len(urls),
                pattern_type=type(detected_pattern).__name__,
            )
            return urls

        # Strategy 3: Selector-based fallback (if selector configured)
        if config.selector:
            logger.warning(
                "pagination_fallback_to_selector",
                seed_url=seed_url,
                selector=config.selector,
                reason="No URL pattern detected, must use DOM-based approach",
            )
            # Selector-based pagination requires actual crawling with DOM parsing
            # This is handled separately by the crawler worker
            # Return seed URL only - worker will handle selector-based pagination
            return [seed_url]

        # No pattern detected and no selector configured
        logger.warning(
            "pagination_pattern_not_detected",
            seed_url=seed_url,
            config_type=config.type,
        )
        return [seed_url]

    async def generate_with_stop_detection(
        self,
        seed_url: str,
        config: PaginationConfig,
        fetch_fn: Callable[[str], Awaitable[tuple[int, bytes]]],
    ) -> AsyncIterator[tuple[str, int, bytes]]:
        """Generate pagination URLs with live stop detection.

        This is an advanced method for sequential crawling with real-time
        stop condition detection. It yields (url, status_code, content) tuples
        and automatically stops when end conditions are met.

        Args:
            seed_url: The seed URL to start from
            config: Pagination configuration
            fetch_fn: Async function that fetches URL and returns (status_code, content)

        Yields:
            Tuples of (url, status_code, content) for each crawled page

        Example:
            >>> async def fetch(url: str) -> tuple[int, bytes]:
            ...     response = await httpx.get(url)
            ...     return response.status_code, response.content
            >>>
            >>> async for url, status, content in service.generate_with_stop_detection(
            ...     seed_url="https://example.com/products?page=5",
            ...     config=pagination_config,
            ...     fetch_fn=fetch
            ... ):
            ...     # Process page content
            ...     print(f"Crawled {url}: {len(content)} bytes")
        """
        if not config.enabled:
            # Just fetch the seed URL once
            status_code, content = await fetch_fn(seed_url)
            yield seed_url, status_code, content
            return

        # Initialize stop detector with config values
        stop_detector = PaginationStopDetector(
            min_content_length=(
                config.min_content_length
                if config.min_content_length is not None
                else self.DEFAULT_MIN_CONTENT_LENGTH
            ),
            max_empty_responses=(
                config.max_empty_responses
                if config.max_empty_responses is not None
                else self.DEFAULT_MAX_EMPTY_RESPONSES
            ),
            track_content_hashes=(
                config.track_content_hashes
                if config.track_content_hashes is not None
                else True
            ),
            track_urls=config.track_urls if config.track_urls is not None else True,
        )

        # Generate URLs
        urls = self.generate_pagination_urls(seed_url, config)

        logger.info(
            "starting_pagination_crawl_with_stop_detection",
            seed_url=seed_url,
            total_urls=len(urls),
            max_pages=config.max_pages,
        )

        # Crawl each URL with stop detection
        for i, url in enumerate(urls, 1):
            try:
                status_code, content = await fetch_fn(url)

                # Check stop conditions
                stop_result: StopCondition = stop_detector.check_response(
                    status_code=status_code, content=content, url=url
                )

                if stop_result.should_stop:
                    logger.info(
                        "pagination_stopped",
                        url=url,
                        reason=stop_result.reason,
                        pages_crawled=i,
                        total_planned=len(urls),
                    )
                    return

                # Yield successful page
                yield url, status_code, content

                logger.debug(
                    "pagination_page_crawled",
                    url=url,
                    page_number=i,
                    status_code=status_code,
                    content_size=len(content),
                )

            except Exception as e:
                logger.error(
                    "pagination_fetch_error",
                    url=url,
                    page_number=i,
                    error=str(e),
                )
                # Continue to next page on error (configurable behavior)
                # Could also stop here depending on requirements
                continue

        logger.info(
            "pagination_crawl_completed",
            seed_url=seed_url,
            total_pages_crawled=len(urls),
        )

    def should_use_selector_based_pagination(self, seed_url: str, config: PaginationConfig) -> bool:
        """Determine if selector-based pagination should be used.

        Selector-based pagination is slower but necessary when:
        - No URL pattern can be detected
        - URL template is not provided
        - Selector is explicitly configured

        Args:
            seed_url: The seed URL
            config: Pagination configuration

        Returns:
            True if selector-based pagination should be used, False otherwise
        """
        if not config.enabled:
            return False

        # If url_template provided, use it (not selector-based)
        if config.url_template:
            return False

        # Try to detect pattern
        pattern = self.detector.detect(seed_url)
        if pattern:
            # Pattern detected, can use URL generation
            return False

        # No pattern detected - check if selector configured
        # Selector can be used for any type, not just next_button
        if config.selector:
            return True

        return False

    def get_pagination_strategy(self, seed_url: str, config: PaginationConfig) -> str:
        """Get the pagination strategy that will be used.

        Args:
            seed_url: The seed URL
            config: Pagination configuration

        Returns:
            Strategy name: "disabled", "template", "auto_detected", or "selector"
        """
        if not config.enabled:
            return "disabled"

        if config.url_template:
            return "template"

        pattern = self.detector.detect(seed_url)
        if pattern:
            return "auto_detected"

        if config.selector:
            return "selector"

        return "disabled"
