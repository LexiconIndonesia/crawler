# Seed URL Crawler - Implementation Summary

## Overview

Implemented a comprehensive seed URL crawling service (`SeedURLCrawler`) that orchestrates the complete workflow for crawling seed URLs with pagination, URL extraction, and robust error handling.

## Features Implemented

### Core Service (`crawler/services/seed_url_crawler.py`)

The `SeedURLCrawler` service provides:

1. **Seed URL Validation and Fetching**
   - Validates crawler configuration
   - Fetches seed URL with proper error handling
   - Immediately fails on 404 errors (as per requirements)
   - Handles HTTP errors (500, 403, etc.) gracefully

2. **Pagination Detection and Handling**
   - Auto-detects pagination patterns from URLs
   - Uses explicit URL templates when configured
   - Falls back to selector-based pagination
   - Handles single-page mode when no pagination detected

3. **Detail URL Extraction**
   - Extracts URLs from list pages using configured selectors
   - Supports container-based extraction for accurate metadata association
   - Deduplicates URLs across pages
   - Resolves relative URLs correctly

4. **Comprehensive Error Handling**
   - **404 Errors**: Fails immediately with `SEED_URL_404` outcome
   - **No URLs Found**: Completes with `SUCCESS_NO_URLS` and warning
   - **Invalid Configuration**: Returns `INVALID_CONFIG` with detailed message
   - **Pagination Selector Not Found**: Falls back to single-page mode with warning
   - **Circular Pagination**: Detected via duplicate content hashing
   - **Max Pages Limit**: Respects configured `max_pages` setting
   - **Empty Pages**: Stops after consecutive empty responses
   - **Network Errors**: Graceful handling with appropriate error messages

5. **Comprehensive Logging**
   - Structured logging for all operations
   - Debug logs for pagination progress
   - Warning logs for edge cases
   - Error logs with full context

## API

### Main Classes

```python
class SeedURLCrawler:
    """Service for crawling seed URLs with comprehensive error handling."""

    async def crawl(
        self,
        seed_url: str,
        config: SeedURLCrawlerConfig
    ) -> CrawlResult:
        """Crawl a seed URL and extract detail page URLs."""
```

### Configuration

```python
import httpx
from crawler.services.redis_cache import URLDeduplicationCache

@dataclass
class SeedURLCrawlerConfig:
    """Configuration for seed URL crawler."""

    step: CrawlStep              # Required: The step configuration with selectors
    job_id: str | None           # Optional: Job ID for deduplication tracking
    http_client: httpx.AsyncClient | None  # Optional: Custom HTTP client
    dedup_cache: URLDeduplicationCache | None  # Optional: Deduplication cache
    max_pages: int | None        # Optional: Override max_pages
    request_timeout: int = 30    # Optional: Request timeout in seconds
```

### Result Types

```python
class CrawlOutcome(Enum):
    """Possible outcomes of a seed URL crawl."""

    SUCCESS = "success"                    # Completed successfully with URLs
    SUCCESS_NO_URLS = "success_no_urls"   # Completed but no URLs found
    SEED_URL_404 = "seed_url_404"         # Seed URL returned 404
    SEED_URL_ERROR = "seed_url_error"     # Seed URL fetch failed
    INVALID_CONFIG = "invalid_config"     # Configuration validation failed
    PAGINATION_STOPPED = "pagination_stopped"  # Stopped due to pagination limits
    CIRCULAR_PAGINATION = "circular_pagination"  # Circular pagination detected
    EMPTY_PAGES = "empty_pages"           # Stopped due to empty pages
    PARTIAL_SUCCESS = "partial_success"   # Some pages succeeded, some failed

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
```

## Usage Example

```python
from crawler.services import SeedURLCrawler, SeedURLCrawlerConfig, CrawlOutcome
from crawler.api.generated import CrawlStep, MethodEnum, PaginationConfig, StepConfig

# Create a crawl step configuration
step = CrawlStep(
    name="crawl_products",
    type="crawl",
    description="Crawl product listing",
    method=MethodEnum.http,
    config=StepConfig(
        url="https://example.com/products",
        pagination=PaginationConfig(
            enabled=True,
            max_pages=10,
            min_content_length=100,
            max_empty_responses=2,
        ),
    ),
    selectors={
        "detail_urls": "a.product-link",
        "container": "article.product",  # Optional: for better metadata association
    },
    output={"urls_field": "detail_urls"},
)

# Create crawler configuration
config = SeedURLCrawlerConfig(
    step=step,
    job_id="job-123",
    max_pages=5,  # Override pagination config
)

# Crawl seed URL
crawler = SeedURLCrawler()
result = await crawler.crawl("https://example.com/products?page=1", config)

# Handle result
if result.outcome == CrawlOutcome.SUCCESS:
    print(f"Successfully extracted {result.total_urls_extracted} URLs")
    for url in result.extracted_urls:
        print(f"  - {url.url}")

elif result.outcome == CrawlOutcome.SEED_URL_404:
    print(f"Seed URL not found: {result.error_message}")

elif result.outcome == CrawlOutcome.SUCCESS_NO_URLS:
    print(f"No URLs found on {result.total_pages_crawled} pages")
    if result.warnings:
        for warning in result.warnings:
            print(f"  Warning: {warning}")

elif result.outcome == CrawlOutcome.INVALID_CONFIG:
    print(f"Configuration error: {result.error_message}")
```

## Testing

Comprehensive integration tests cover all scenarios:

### Positive Test Cases (2 tests)
- ✅ Successful single page crawl
- ✅ Successful paginated crawl with auto-detection

### Negative Test Cases (7 tests)
- ✅ Seed URL returns 404 (fails immediately)
- ✅ Seed URL returns 500 (error outcome)
- ✅ No detail URLs found (success with warning)
- ✅ Invalid configuration (no selector)
- ✅ Seed page extraction failure in paginated mode (fatal error)
- ✅ Pagination selector configured but not found
- ✅ Partial success with page extraction errors (some pages fail)

### Edge Cases (5 tests)
- ✅ Max pages limit respected
- ✅ Empty pages stop detection
- ✅ HTTP request errors handled
- ✅ Circular pagination detection (duplicate content)
- ✅ Relative URL resolution

**Total**: 14 tests, all passing ✅

## Integration with Existing Services

The `SeedURLCrawler` integrates seamlessly with:

- **`PaginationService`**: Detects pagination patterns and generates URLs
- **`URLExtractorService`**: Extracts detail URLs from list pages
- **`HTMLParserService`**: Parses HTML and applies selectors
- **`URLDeduplicationCache`**: Deduplicates URLs across crawl sessions
- **`normalize_url()`**: Normalizes URLs for comparison

## Error Handling Matrix

| Error Condition | Outcome | Behavior |
|----------------|---------|----------|
| Seed URL 404 | `SEED_URL_404` | Fail immediately, no pages crawled |
| Seed URL 500/403 | `SEED_URL_ERROR` | Fail immediately with HTTP error |
| Network timeout | `SEED_URL_ERROR` | Fail with connection error |
| No detail URLs found | `SUCCESS_NO_URLS` | Complete with warning |
| Invalid config (no selector) | `INVALID_CONFIG` | Fail with validation error |
| Pagination selector not found | `SUCCESS` or `SUCCESS_NO_URLS` | Single page mode |
| Circular pagination | `SUCCESS` | Stop when duplicate content detected |
| Max pages reached | `SUCCESS` | Stop at max_pages limit |
| Consecutive empty pages | `SUCCESS` | Stop after max_empty_responses |

## Logging Examples

```
# Successful crawl
2025-11-02 09:00:34 [info] seed_url_crawl_started job_id=job-123 seed_url=https://example.com/products
2025-11-02 09:00:34 [info] fetching_seed_url seed_url=https://example.com/products
2025-11-02 09:00:34 [info] seed_url_fetched content_size=12345 status_code=200
2025-11-02 09:00:34 [info] pagination_strategy_determined strategy=auto_detected
2025-11-02 09:00:34 [info] crawling_with_pagination max_pages=10 strategy=auto_detected
2025-11-02 09:00:34 [info] seed_page_urls_extracted urls_count=20
2025-11-02 09:00:35 [info] pagination_page_processed page_number=2 urls_count=20 total_urls=40
2025-11-02 09:00:35 [info] seed_url_crawl_completed outcome=success pages_crawled=3 total_urls=60

# 404 error
2025-11-02 09:00:34 [error] seed_url_404 seed_url=https://example.com/products

# No URLs found
2025-11-02 09:00:34 [warning] no_detail_urls_found pages_crawled=1 seed_url=https://example.com/products

# Pagination selector not found
2025-11-02 09:00:34 [warning] pagination_selector_not_found selector=a.next-page
```

## Files Modified

1. **`crawler/services/seed_url_crawler.py`** (NEW)
   - Main service implementation
   - ~500 lines of code
   - Comprehensive error handling and logging

2. **`crawler/services/__init__.py`** (MODIFIED)
   - Exported new service classes and enums

3. **`tests/integration/services/test_seed_url_crawler.py`** (NEW)
   - 14 comprehensive integration tests
   - Tests all positive, negative, and edge cases
   - ~657 lines of test code

## Acceptance Criteria Status

All acceptance criteria have been met:

- ✅ Handle seed URL returns 404 (fail immediately)
- ✅ Handle pagination selector not found (single page mode)
- ✅ Handle no detail URLs found (log warning, complete)
- ✅ Handle invalid configuration (validation error)
- ✅ Handle circular pagination detection
- ✅ Handle max_pages limit
- ✅ Log all edge cases appropriately
- ✅ Integration tests for positive and negative cases

## Next Steps

The `SeedURLCrawler` service is ready for integration with:

1. **Job execution workflows**: Use in crawl job processing
2. **API endpoints**: Expose via seed URL submission APIs
3. **Scheduled crawls**: Integrate with scheduled job system
4. **Monitoring**: Add metrics for crawl outcomes and performance
