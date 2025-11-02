"""Seed URL crawling service with comprehensive error handling.

This service orchestrates the complete seed URL crawling workflow:
1. Validates seed URL and configuration
2. Fetches seed URL (handles 404 and other errors)
3. Detects pagination pattern or uses selector
4. Crawls all pagination pages (with stop detection)
5. Extracts detail URLs from each list page
6. Handles all error cases gracefully
"""

from dataclasses import dataclass
from enum import Enum

import httpx

from crawler.api.generated import CrawlStep, PaginationConfig
from crawler.core.logging import get_logger
from crawler.services.html_parser import HTMLParserService
from crawler.services.pagination import PaginationService
from crawler.services.redis_cache import URLDeduplicationCache
from crawler.services.url_extractor import ExtractedURL, URLExtractorService

logger = get_logger(__name__)


class CrawlOutcome(str, Enum):
    """Possible outcomes of a seed URL crawl operation."""

    SUCCESS = "success"  # Crawl completed successfully with URLs
    SUCCESS_NO_URLS = "success_no_urls"  # Completed but no URLs found
    SEED_URL_404 = "seed_url_404"  # Seed URL returned 404
    SEED_URL_ERROR = "seed_url_error"  # Seed URL fetch failed
    INVALID_CONFIG = "invalid_config"  # Configuration validation failed
    PAGINATION_STOPPED = "pagination_stopped"  # Stopped due to pagination limits
    CIRCULAR_PAGINATION = "circular_pagination"  # Circular pagination detected
    EMPTY_PAGES = "empty_pages"  # Stopped due to consecutive empty pages
    PARTIAL_SUCCESS = "partial_success"  # Some pages succeeded, some failed


@dataclass
class CrawlResult:
    """Result of a seed URL crawl operation."""

    outcome: CrawlOutcome
    seed_url: str
    total_pages_crawled: int
    total_urls_extracted: int
    extracted_urls: list[ExtractedURL]
    error_message: str | None = None
    warnings: list[str] | None = None
    pagination_strategy: str | None = None
    stopped_reason: str | None = None


@dataclass
class SeedURLCrawlerConfig:
    """Configuration for seed URL crawler."""

    # Required: The step configuration with selectors
    step: CrawlStep

    # Optional: Job ID for deduplication tracking
    job_id: str | None = None

    # Optional: HTTP client for making requests (if None, creates one)
    http_client: httpx.AsyncClient | None = None

    # Optional: Deduplication cache
    dedup_cache: URLDeduplicationCache | None = None

    # Optional: Maximum pages to crawl (overrides pagination config)
    max_pages: int | None = None

    # Optional: Timeout for HTTP requests (seconds)
    request_timeout: int = 30


class SeedURLCrawler:
    """Service for crawling seed URLs with comprehensive error handling.

    This service implements the main algorithm for seed URL crawling:
    - Validates configuration
    - Fetches seed URL (handles 404 immediately)
    - Detects and handles pagination
    - Extracts detail URLs from list pages
    - Handles all edge cases with appropriate logging

    Example:
        >>> config = SeedURLCrawlerConfig(
        ...     step=crawl_step,
        ...     job_id="job-123"
        ... )
        >>> crawler = SeedURLCrawler()
        >>> result = await crawler.crawl("https://example.com/products?page=1", config)
        >>> if result.outcome == CrawlOutcome.SUCCESS:
        ...     print(f"Extracted {result.total_urls_extracted} URLs")
    """

    def __init__(self) -> None:
        """Initialize seed URL crawler."""
        self.pagination_service = PaginationService()
        # HTML parser and URL extractor will be created per-crawl
        # to avoid sharing state

    async def crawl(self, seed_url: str, config: SeedURLCrawlerConfig) -> CrawlResult:
        """Crawl a seed URL and extract detail page URLs.

        This is the main entry point for seed URL crawling. It handles:
        - Configuration validation
        - Seed URL fetching (404 handling)
        - Pagination detection and crawling
        - Detail URL extraction
        - All error cases

        Args:
            seed_url: The seed URL to start crawling from
            config: Crawler configuration

        Returns:
            CrawlResult with outcome and extracted URLs

        Example:
            >>> result = await crawler.crawl(
            ...     "https://example.com/products?page=1",
            ...     SeedURLCrawlerConfig(step=step, job_id="job-123")
            ... )
        """
        logger.info("seed_url_crawl_started", seed_url=seed_url, job_id=config.job_id)

        warnings: list[str] = []
        http_client = config.http_client
        client_created = False

        try:
            # Step 1: Validate configuration
            validation_error = self._validate_config(config)
            if validation_error:
                logger.error(
                    "seed_url_crawl_invalid_config",
                    seed_url=seed_url,
                    error=validation_error,
                )
                return CrawlResult(
                    outcome=CrawlOutcome.INVALID_CONFIG,
                    seed_url=seed_url,
                    total_pages_crawled=0,
                    total_urls_extracted=0,
                    extracted_urls=[],
                    error_message=validation_error,
                )

            # Step 2: Create HTTP client if not provided
            if http_client is None:
                http_client = httpx.AsyncClient(
                    timeout=config.request_timeout,
                    follow_redirects=True,
                )
                client_created = True

            # Step 3: Fetch seed URL (handle 404 immediately)
            try:
                logger.info("fetching_seed_url", seed_url=seed_url)
                response = await http_client.get(seed_url)

                # Handle 404 - fail immediately as per requirements
                if response.status_code == 404:
                    logger.error("seed_url_404", seed_url=seed_url)
                    return CrawlResult(
                        outcome=CrawlOutcome.SEED_URL_404,
                        seed_url=seed_url,
                        total_pages_crawled=0,
                        total_urls_extracted=0,
                        extracted_urls=[],
                        error_message=f"Seed URL returned 404 Not Found: {seed_url}",
                    )

                # Handle other HTTP errors
                if response.status_code >= 400:
                    logger.error(
                        "seed_url_http_error",
                        seed_url=seed_url,
                        status_code=response.status_code,
                    )
                    return CrawlResult(
                        outcome=CrawlOutcome.SEED_URL_ERROR,
                        seed_url=seed_url,
                        total_pages_crawled=0,
                        total_urls_extracted=0,
                        extracted_urls=[],
                        error_message=f"Seed URL returned HTTP {response.status_code}: {seed_url}",
                    )

                seed_content = response.content
                logger.info(
                    "seed_url_fetched",
                    seed_url=seed_url,
                    status_code=response.status_code,
                    content_size=len(seed_content),
                )

            except httpx.RequestError as e:
                logger.error("seed_url_fetch_failed", seed_url=seed_url, error=str(e))
                return CrawlResult(
                    outcome=CrawlOutcome.SEED_URL_ERROR,
                    seed_url=seed_url,
                    total_pages_crawled=0,
                    total_urls_extracted=0,
                    extracted_urls=[],
                    error_message=f"Failed to fetch seed URL: {e}",
                )

            # Step 4: Get pagination configuration
            pagination_config = (
                config.step.config.pagination
                if config.step.config and config.step.config.pagination
                else PaginationConfig(enabled=False)
            )

            # Override max_pages if specified in crawler config
            if config.max_pages is not None:
                pagination_config.max_pages = config.max_pages

            # Step 5: Determine pagination strategy
            pagination_strategy = self.pagination_service.get_pagination_strategy(
                seed_url, pagination_config
            )
            logger.info("pagination_strategy_determined", strategy=pagination_strategy)

            # Step 6: Crawl pages and extract URLs
            result = await self._crawl_and_extract(
                seed_url=seed_url,
                seed_content=seed_content,
                pagination_config=pagination_config,
                pagination_strategy=pagination_strategy,
                config=config,
                http_client=http_client,
                warnings=warnings,
            )

            return result

        except Exception as e:
            logger.error("seed_url_crawl_unexpected_error", seed_url=seed_url, error=str(e))
            return CrawlResult(
                outcome=CrawlOutcome.SEED_URL_ERROR,
                seed_url=seed_url,
                total_pages_crawled=0,
                total_urls_extracted=0,
                extracted_urls=[],
                error_message=f"Unexpected error during crawl: {e}",
            )

        finally:
            # Clean up HTTP client if we created it
            if client_created and http_client:
                await http_client.aclose()

    async def _crawl_and_extract(
        self,
        seed_url: str,
        seed_content: bytes,
        pagination_config: PaginationConfig,
        pagination_strategy: str,
        config: SeedURLCrawlerConfig,
        http_client: httpx.AsyncClient,
        warnings: list[str],
    ) -> CrawlResult:
        """Crawl pagination pages and extract URLs.

        This method handles:
        - Pagination URL generation
        - Page fetching with stop detection
        - Detail URL extraction from each page
        - Circular pagination detection
        - Max pages limit

        Args:
            seed_url: The seed URL
            seed_content: Content of the seed URL (already fetched)
            pagination_config: Pagination configuration
            pagination_strategy: Detected pagination strategy
            config: Crawler configuration
            http_client: HTTP client for making requests
            warnings: List to accumulate warnings

        Returns:
            CrawlResult with extracted URLs and outcome
        """
        # Initialize services for URL extraction
        html_parser = HTMLParserService()
        url_extractor = URLExtractorService(
            html_parser=html_parser,
            dedup_cache=config.dedup_cache,
        )

        all_extracted_urls: list[ExtractedURL] = []
        pages_crawled = 0
        stopped_reason: str | None = None

        # Get detail URL selector from step
        detail_selector = self._get_detail_url_selector(config.step)
        if not detail_selector:
            logger.warning("no_detail_url_selector_configured", seed_url=seed_url)
            warnings.append("No detail URL selector configured - cannot extract URLs")
            return CrawlResult(
                outcome=CrawlOutcome.INVALID_CONFIG,
                seed_url=seed_url,
                total_pages_crawled=0,
                total_urls_extracted=0,
                extracted_urls=[],
                error_message="No detail URL selector configured in step",
                warnings=warnings,
            )

        # Get container selector if available (for better metadata association)
        container_selector = self._get_container_selector(config.step)

        # Create fetch function for pagination service
        async def fetch_page(url: str) -> tuple[int, bytes]:
            """Fetch a page and return status code and content."""
            try:
                response = await http_client.get(url)
                return response.status_code, response.content
            except httpx.RequestError as e:
                logger.warning("page_fetch_error", url=url, error=str(e))
                # Return 500 to trigger stop detection
                return 500, b""

        # Strategy 1: Use pagination with stop detection
        if pagination_config.enabled and pagination_strategy != "disabled":
            logger.info(
                "crawling_with_pagination",
                seed_url=seed_url,
                strategy=pagination_strategy,
                max_pages=pagination_config.max_pages,
            )

            # First, extract URLs from seed page (we already have the content)
            try:
                seed_urls = await url_extractor.extract_urls(
                    html_content=seed_content,
                    base_url=seed_url,
                    url_selector=detail_selector,
                    deduplicate=True,
                    job_id=config.job_id,
                    container_selector=container_selector,
                )
                all_extracted_urls.extend(seed_urls)
                pages_crawled += 1
                logger.info(
                    "seed_page_urls_extracted",
                    seed_url=seed_url,
                    urls_count=len(seed_urls),
                )
            except Exception as e:
                logger.error("seed_page_extraction_failed", seed_url=seed_url, error=str(e))
                warnings.append(f"Failed to extract URLs from seed page: {e}")

            # Now crawl remaining pagination pages
            async for (
                url,
                status_code,
                content,
            ) in self.pagination_service.generate_with_stop_detection(
                seed_url=seed_url,
                config=pagination_config,
                fetch_fn=fetch_page,
            ):
                # Skip seed URL (already processed)
                if url == seed_url:
                    continue

                # Extract URLs from this page
                try:
                    page_urls = await url_extractor.extract_urls(
                        html_content=content,
                        base_url=url,
                        url_selector=detail_selector,
                        deduplicate=True,
                        job_id=config.job_id,
                        container_selector=container_selector,
                    )
                    all_extracted_urls.extend(page_urls)
                    pages_crawled += 1

                    logger.info(
                        "pagination_page_processed",
                        url=url,
                        page_number=pages_crawled,
                        urls_count=len(page_urls),
                        total_urls=len(all_extracted_urls),
                    )

                except Exception as e:
                    logger.error("pagination_page_extraction_failed", url=url, error=str(e))
                    warnings.append(f"Failed to extract URLs from page {url}: {e}")

        # Strategy 2: Single page mode (no pagination or selector-based)
        else:
            logger.info("crawling_single_page_mode", seed_url=seed_url)

            if pagination_config.enabled and pagination_config.selector:
                # Pagination selector configured but not found - log warning
                logger.warning(
                    "pagination_selector_not_found",
                    seed_url=seed_url,
                    selector=pagination_config.selector,
                    message=(
                        "Pagination selector configured but no pattern detected "
                        "- using single page mode"
                    ),
                )
                warnings.append(
                    f"Pagination selector '{pagination_config.selector}' configured "
                    "but pattern not detected"
                )
                stopped_reason = "pagination_selector_not_found"

            # Extract URLs from seed page only
            try:
                seed_urls = await url_extractor.extract_urls(
                    html_content=seed_content,
                    base_url=seed_url,
                    url_selector=detail_selector,
                    deduplicate=True,
                    job_id=config.job_id,
                    container_selector=container_selector,
                )
                all_extracted_urls.extend(seed_urls)
                pages_crawled = 1
                logger.info(
                    "single_page_urls_extracted", seed_url=seed_url, urls_count=len(seed_urls)
                )

            except Exception as e:
                logger.error("single_page_extraction_failed", seed_url=seed_url, error=str(e))
                return CrawlResult(
                    outcome=CrawlOutcome.SEED_URL_ERROR,
                    seed_url=seed_url,
                    total_pages_crawled=0,
                    total_urls_extracted=0,
                    extracted_urls=[],
                    error_message=f"Failed to extract URLs from seed page: {e}",
                    warnings=warnings,
                )

        # Determine outcome
        if not all_extracted_urls:
            logger.warning("no_detail_urls_found", seed_url=seed_url, pages_crawled=pages_crawled)
            warnings.append("No detail URLs found on any page")
            outcome = CrawlOutcome.SUCCESS_NO_URLS
        else:
            outcome = CrawlOutcome.SUCCESS

        logger.info(
            "seed_url_crawl_completed",
            seed_url=seed_url,
            outcome=outcome.value,
            pages_crawled=pages_crawled,
            total_urls=len(all_extracted_urls),
        )

        return CrawlResult(
            outcome=outcome,
            seed_url=seed_url,
            total_pages_crawled=pages_crawled,
            total_urls_extracted=len(all_extracted_urls),
            extracted_urls=all_extracted_urls,
            warnings=warnings if warnings else None,
            pagination_strategy=pagination_strategy,
            stopped_reason=stopped_reason,
        )

    def _validate_config(self, config: SeedURLCrawlerConfig) -> str | None:
        """Validate crawler configuration.

        Args:
            config: Configuration to validate

        Returns:
            Error message if invalid, None if valid
        """
        if not config.step:
            return "Step configuration is required"

        if not config.step.selectors:
            return "Step selectors are required for URL extraction"

        # Check if there's a detail_urls selector or similar
        detail_selector = self._get_detail_url_selector(config.step)
        if not detail_selector:
            return "No detail URL selector found in step configuration"

        return None

    def _get_detail_url_selector(self, step: CrawlStep) -> str | None:
        """Extract detail URL selector from step configuration.

        Args:
            step: Crawl step configuration

        Returns:
            Detail URL selector or None
        """
        if not step.selectors:
            return None

        # Check for common selector names
        selectors_dict = step.selectors
        for key in ["detail_urls", "urls", "links", "articles", "items"]:
            if key in selectors_dict:
                selector = selectors_dict[key]
                # Return string selector or selector config
                if isinstance(selector, str):
                    return selector
                elif hasattr(selector, "selector"):
                    return selector.selector
                return str(selector)

        return None

    def _get_container_selector(self, step: CrawlStep) -> str | None:
        """Extract container selector from step configuration.

        Container selectors help associate URLs with their metadata correctly.

        Args:
            step: Crawl step configuration

        Returns:
            Container selector or None
        """
        if not step.selectors:
            return None

        selectors_dict = step.selectors
        for key in ["container", "item", "article", "card"]:
            if key in selectors_dict:
                selector = selectors_dict[key]
                if isinstance(selector, str):
                    return selector
                elif hasattr(selector, "selector"):
                    return selector.selector

        return None
