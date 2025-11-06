"""Integration tests for SeedURLCrawler service.

Tests cover:
- Positive cases: successful crawls with pagination, single page, etc.
- Negative cases: 404 errors, no URLs found, invalid config, etc.
- Edge cases: circular pagination, max pages limit, empty pages
"""

from collections.abc import Callable
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from crawler.api.generated import CrawlStep, MethodEnum, PaginationConfig, StepConfig
from crawler.services import CrawlOutcome, SeedURLCrawler, SeedURLCrawlerConfig


def create_mock_http_client(
    responses: dict[str, tuple[int, bytes | str]] | Callable[[str], tuple[int, bytes | str]],
) -> AsyncMock:
    """Create a mock HTTP client with predefined responses.

    Args:
        responses: Either a dict mapping URLs to (status_code, content) tuples,
                  or a callable that takes a URL and returns (status_code, content)

    Returns:
        Mock HTTP client
    """
    mock_client = AsyncMock(spec=httpx.AsyncClient)

    async def mock_get(url: str) -> Mock:
        """Mock get method that returns appropriate response for URL."""
        if callable(responses):
            status_code, content = responses(url)
        else:
            status_code, content = responses.get(url, (404, b"Not Found"))

        # Convert string content to bytes if needed
        if isinstance(content, str):
            content = content.encode("utf-8")

        mock_response = Mock(spec=httpx.Response)
        mock_response.status_code = status_code
        mock_response.content = content
        return mock_response

    mock_client.get = mock_get
    mock_client.aclose = AsyncMock()
    return mock_client


@pytest.fixture
def seed_url_crawler() -> SeedURLCrawler:
    """Create a SeedURLCrawler instance for testing."""
    return SeedURLCrawler()


@pytest.fixture
def basic_crawl_step() -> CrawlStep:
    """Create a basic crawl step with detail URL selector."""
    return CrawlStep(
        name="crawl_list",
        type="crawl",
        description="Crawl list page",
        method=MethodEnum.http,
        config=StepConfig(
            url="https://example.com/products",
            pagination=PaginationConfig(enabled=False),
        ),
        selectors={"detail_urls": "a.product-link"},
        output={"urls_field": "detail_urls"},
    )


@pytest.fixture
def paginated_crawl_step() -> CrawlStep:
    """Create a crawl step with pagination enabled."""
    return CrawlStep(
        name="crawl_list",
        type="crawl",
        description="Crawl list page with pagination",
        method=MethodEnum.http,
        config=StepConfig(
            url="https://example.com/products",
            pagination=PaginationConfig(
                enabled=True,
                max_pages=5,
                min_content_length=100,
                max_empty_responses=2,
            ),
        ),
        selectors={"detail_urls": "a.product-link"},
        output={"urls_field": "detail_urls"},
    )


# =============================================================================
# Positive Test Cases
# =============================================================================


@pytest.mark.asyncio
async def test_successful_single_page_crawl(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test successful crawl of a single page with URLs."""
    seed_url = "https://example.com/products"

    html_content = b"""
    <html>
        <body>
            <a class="product-link" href="/product/1">Product 1</a>
            <a class="product-link" href="/product/2">Product 2</a>
            <a class="product-link" href="/product/3">Product 3</a>
        </body>
    </html>
    """

    mock_client = create_mock_http_client({seed_url: (200, html_content)})

    config = SeedURLCrawlerConfig(
        step=basic_crawl_step, job_id="test-job-1", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS
    assert result.total_pages_crawled == 1
    assert result.total_urls_extracted == 3
    assert len(result.extracted_urls) == 3
    assert result.error_message is None
    assert all(url.url.startswith("https://example.com/product/") for url in result.extracted_urls)


@pytest.mark.asyncio
async def test_successful_paginated_crawl(
    seed_url_crawler: SeedURLCrawler,
    paginated_crawl_step: CrawlStep,
) -> None:
    """Test successful crawl with pagination detection."""
    seed_url = "https://example.com/products?page=1"

    def get_response(url: str) -> tuple[int, bytes]:
        """Generate response based on URL."""
        if "page=1" in url:
            return (
                200,
                b"""
                <html><body>
                    <a class="product-link" href="/product/11">Product 11</a>
                    <a class="product-link" href="/product/12">Product 12</a>
                </body></html>
            """,
            )
        elif "page=2" in url:
            return (
                200,
                b"""
                <html><body>
                    <a class="product-link" href="/product/21">Product 21</a>
                    <a class="product-link" href="/product/22">Product 22</a>
                </body></html>
            """,
            )
        elif "page=3" in url:
            return (
                200,
                b"""
                <html><body>
                    <a class="product-link" href="/product/31">Product 31</a>
                    <a class="product-link" href="/product/32">Product 32</a>
                </body></html>
            """,
            )
        else:
            return (404, b"Not Found")

    mock_client = create_mock_http_client(get_response)

    config = SeedURLCrawlerConfig(
        step=paginated_crawl_step, job_id="test-job-2", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS
    assert result.total_pages_crawled == 3
    assert result.total_urls_extracted == 6
    assert result.pagination_strategy == "auto_detected"


# =============================================================================
# Negative Test Cases
# =============================================================================


@pytest.mark.asyncio
async def test_seed_url_returns_404(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test handling of 404 error on seed URL - should fail immediately."""
    seed_url = "https://example.com/products"

    mock_client = create_mock_http_client({seed_url: (404, b"Not Found")})

    config = SeedURLCrawlerConfig(
        step=basic_crawl_step, job_id="test-job-404", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SEED_URL_404
    assert result.total_pages_crawled == 0
    assert result.total_urls_extracted == 0
    assert "404 Not Found" in result.error_message
    assert len(result.extracted_urls) == 0


@pytest.mark.asyncio
async def test_seed_url_returns_500(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test handling of 500 error on seed URL."""
    seed_url = "https://example.com/products"

    mock_client = create_mock_http_client({seed_url: (500, b"Internal Server Error")})

    config = SeedURLCrawlerConfig(
        step=basic_crawl_step, job_id="test-job-500", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SEED_URL_ERROR
    assert result.total_pages_crawled == 0
    assert "HTTP 500" in result.error_message


@pytest.mark.asyncio
async def test_no_detail_urls_found(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test handling when no detail URLs are found - should complete with warning."""
    seed_url = "https://example.com/products"

    html_content = b"""
    <html>
        <body>
            <p>No products available</p>
        </body>
    </html>
    """

    mock_client = create_mock_http_client({seed_url: (200, html_content)})

    config = SeedURLCrawlerConfig(
        step=basic_crawl_step, job_id="test-job-no-urls", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS_NO_URLS
    assert result.total_pages_crawled == 1
    assert result.total_urls_extracted == 0
    assert len(result.extracted_urls) == 0
    assert result.warnings is not None
    assert any("No detail URLs found" in w for w in result.warnings)


@pytest.mark.asyncio
async def test_invalid_config_no_selector(
    seed_url_crawler: SeedURLCrawler,
) -> None:
    """Test validation error when no detail URL selector is configured."""
    seed_url = "https://example.com/products"

    step = CrawlStep(
        name="crawl_list",
        type="crawl",
        description="Invalid step",
        method=MethodEnum.http,
        config=StepConfig(url=seed_url, pagination=PaginationConfig(enabled=False)),
        selectors={},  # No selectors!
        output={"urls_field": "detail_urls"},
    )

    config = SeedURLCrawlerConfig(step=step, job_id="test-job-invalid")
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.INVALID_CONFIG
    assert result.total_pages_crawled == 0
    assert "missing required 'detail_urls' selector" in result.error_message.lower()


@pytest.mark.asyncio
async def test_seed_page_extraction_failure_in_paginated_mode(
    seed_url_crawler: SeedURLCrawler,
    paginated_crawl_step: CrawlStep,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test that seed page extraction failure is fatal in paginated mode.

    Ensures consistency with single-page mode - if the seed page cannot be
    processed, the entire crawl should fail immediately.
    """
    seed_url = "https://example.com/products?page=1"

    # Return valid HTML so seed URL fetch succeeds
    valid_html = b"""
    <html><body>
        <a class="product-link" href="/product/1">Product 1</a>
    </body></html>
    """

    mock_client = create_mock_http_client({seed_url: (200, valid_html)})

    # Patch the _extract_urls_from_content method to raise an exception on seed page
    original_extract = seed_url_crawler._extract_urls_from_content
    call_count = 0

    async def failing_extract(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:  # Fail on first call (seed page)
            raise RuntimeError("Simulated extraction failure on seed page")
        return await original_extract(*args, **kwargs)

    monkeypatch.setattr(seed_url_crawler, "_extract_urls_from_content", failing_extract)

    config = SeedURLCrawlerConfig(
        step=paginated_crawl_step, job_id="test-job-seed-fail", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    # Should fail immediately with SEED_URL_ERROR
    assert result.outcome == CrawlOutcome.SEED_URL_ERROR
    assert result.total_pages_crawled == 0
    assert result.total_urls_extracted == 0
    assert "Failed to extract URLs from seed page" in result.error_message
    assert "Simulated extraction failure" in result.error_message


@pytest.mark.asyncio
async def test_pagination_selector_not_found(
    seed_url_crawler: SeedURLCrawler,
) -> None:
    """Test single page mode when pagination selector is configured but not found."""
    seed_url = "https://example.com/products"

    step = CrawlStep(
        name="crawl_list",
        type="crawl",
        description="Crawl with selector",
        method=MethodEnum.http,
        config=StepConfig(
            url=seed_url,
            pagination=PaginationConfig(
                enabled=True,
                selector="a.next-page",
            ),
        ),
        selectors={"detail_urls": "a.product-link"},
        output={"urls_field": "detail_urls"},
    )

    html_content = b"""
    <html>
        <body>
            <a class="product-link" href="/product/1">Product 1</a>
        </body>
    </html>
    """

    mock_client = create_mock_http_client({seed_url: (200, html_content)})

    config = SeedURLCrawlerConfig(step=step, job_id="test-job-selector", http_client=mock_client)
    result = await seed_url_crawler.crawl(seed_url, config)

    # When pagination selector is configured but not found, warnings are generated
    # Since URLs are extracted, outcome is PARTIAL_SUCCESS (not SUCCESS)
    assert result.outcome == CrawlOutcome.PARTIAL_SUCCESS
    assert result.total_pages_crawled == 1
    assert result.total_urls_extracted == 1
    assert result.warnings is not None
    assert any("no additional pages found" in w for w in result.warnings)
    # When selector is configured, pagination_strategy is "selector"
    # This means selector-based pagination is being used (even if it only finds seed page)
    assert result.pagination_strategy == "selector"


@pytest.mark.asyncio
async def test_partial_success_with_page_extraction_errors(
    seed_url_crawler: SeedURLCrawler,
    paginated_crawl_step: CrawlStep,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test PARTIAL_SUCCESS outcome when some pages succeed but others fail during extraction.

    This test simulates a scenario where:
    - Seed page (page 1) extraction succeeds
    - Page 2 extraction fails with an error
    - Page 3 extraction succeeds
    - Overall outcome should be PARTIAL_SUCCESS with warnings
    """
    seed_url = "https://example.com/products?page=1"

    def get_response(url: str) -> tuple[int, bytes]:
        """All pages return valid HTML."""
        if "page=1" in url:
            return (
                200,
                b"""
                <html><body>
                    <a class="product-link" href="/product/1">Product 1</a>
                    <a class="product-link" href="/product/2">Product 2</a>
                </body></html>
            """,
            )
        elif "page=2" in url:
            return (
                200,
                b"""
                <html><body>
                    <a class="product-link" href="/product/3">Product 3</a>
                </body></html>
            """,
            )
        elif "page=3" in url:
            return (
                200,
                b"""
                <html><body>
                    <a class="product-link" href="/product/4">Product 4</a>
                    <a class="product-link" href="/product/5">Product 5</a>
                </body></html>
            """,
            )
        else:
            return (404, b"Not Found")

    mock_client = create_mock_http_client(get_response)

    # Patch _extract_urls_from_content to fail on page 2
    original_extract = seed_url_crawler._extract_urls_from_content
    call_count = 0

    async def failing_extract(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        base_url = kwargs.get("base_url", "")

        # Fail on page 2 (second pagination page, after seed page)
        if "page=2" in base_url:
            raise RuntimeError("Simulated extraction error on page 2")

        return await original_extract(*args, **kwargs)

    monkeypatch.setattr(seed_url_crawler, "_extract_urls_from_content", failing_extract)

    config = SeedURLCrawlerConfig(
        step=paginated_crawl_step, job_id="test-job-partial", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    # Should have PARTIAL_SUCCESS: some URLs extracted but warnings present
    assert result.outcome == CrawlOutcome.PARTIAL_SUCCESS
    assert result.total_urls_extracted == 4  # Page 1 (2 URLs) + Page 3 (2 URLs), page 2 failed
    assert result.total_pages_crawled == 2  # Page 1 succeeded, page 2 failed, page 3 succeeded
    assert result.warnings is not None
    assert any("Failed to extract URLs from page" in w for w in result.warnings)
    assert any("page=2" in w for w in result.warnings)


# =============================================================================
# Edge Cases
# =============================================================================


@pytest.mark.asyncio
async def test_max_pages_limit(
    seed_url_crawler: SeedURLCrawler,
) -> None:
    """Test that max_pages limit is respected."""
    seed_url = "https://example.com/products?page=1"

    step = CrawlStep(
        name="crawl_list",
        type="crawl",
        description="Crawl with limit",
        method=MethodEnum.http,
        config=StepConfig(
            url=seed_url,
            pagination=PaginationConfig(
                enabled=True,
                max_pages=3,
            ),
        ),
        selectors={"detail_urls": "a.product-link"},
        output={"urls_field": "detail_urls"},
    )

    def get_response(url: str) -> tuple[int, bytes]:
        """Generate response for 5 pages."""
        for page_num in range(1, 6):
            if f"page={page_num}" in url:
                return (
                    200,
                    f"""
                    <html><body>
                        <a class="product-link" href="/product/{page_num}">Product {page_num}</a>
                    </body></html>
                """.encode(),
                )
        return (404, b"Not Found")

    mock_client = create_mock_http_client(get_response)

    config = SeedURLCrawlerConfig(step=step, job_id="test-job-max-pages", http_client=mock_client)
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS
    assert result.total_pages_crawled == 3
    assert result.total_urls_extracted == 3


@pytest.mark.asyncio
async def test_empty_pages_stop_detection(
    seed_url_crawler: SeedURLCrawler,
    paginated_crawl_step: CrawlStep,
) -> None:
    """Test that consecutive empty pages trigger stop condition."""
    seed_url = "https://example.com/products?page=1"

    def get_response(url: str) -> tuple[int, bytes]:
        """Page 1 has content, pages 2+ are empty."""
        if "page=1" in url:
            return (
                200,
                b"""
                <html><body>
                    <a class="product-link" href="/product/1">Product 1</a>
                </body></html>
            """,
            )
        else:
            # Empty pages (below min_content_length of 100)
            return (200, b"<html><body></body></html>")

    mock_client = create_mock_http_client(get_response)

    config = SeedURLCrawlerConfig(
        step=paginated_crawl_step, job_id="test-job-empty", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS
    # Seed page (1) + 1 empty page (2) before stop condition is met
    # Stop triggers when the second empty page is encountered (max_empty_responses=2)
    assert result.total_pages_crawled == 2


@pytest.mark.asyncio
async def test_http_request_error(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test handling of network/request errors."""
    seed_url = "https://example.com/products"

    # Create mock client that raises exception
    mock_client = AsyncMock(spec=httpx.AsyncClient)
    mock_client.get = AsyncMock(side_effect=httpx.RequestError("Connection timeout"))
    mock_client.aclose = AsyncMock()

    config = SeedURLCrawlerConfig(
        step=basic_crawl_step, job_id="test-job-error", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SEED_URL_ERROR
    assert result.total_pages_crawled == 0
    assert "Failed to fetch seed URL" in result.error_message


@pytest.mark.asyncio
async def test_circular_pagination_detection(
    seed_url_crawler: SeedURLCrawler,
    paginated_crawl_step: CrawlStep,
) -> None:
    """Test detection of circular pagination via duplicate content."""
    seed_url = "https://example.com/products?page=1"

    page1_content = b"""
    <html><body>
        <a class="product-link" href="/product/1">Product 1</a>
    </body></html>
    """

    page2_content = b"""
    <html><body>
        <a class="product-link" href="/product/2">Product 2</a>
    </body></html>
    """

    def get_response(url: str) -> tuple[int, bytes]:
        """Page 3 returns same content as page 1 (circular)."""
        if "page=1" in url or "page=3" in url:
            return (200, page1_content)
        elif "page=2" in url:
            return (200, page2_content)
        else:
            return (404, b"Not Found")

    mock_client = create_mock_http_client(get_response)

    config = SeedURLCrawlerConfig(
        step=paginated_crawl_step, job_id="test-job-circular", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS
    # Should process page 1 (unique) and page 2 (unique)
    # Stop when page 3 is detected as duplicate content
    assert result.total_pages_crawled == 2


@pytest.mark.asyncio
async def test_relative_url_resolution(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test that relative URLs are resolved correctly."""
    seed_url = "https://example.com/products"

    html_content = b"""
    <html><body>
        <a class="product-link" href="/product/1">Product 1</a>
        <a class="product-link" href="../product/2">Product 2</a>
        <a class="product-link" href="product/3">Product 3</a>
    </body></html>
    """

    mock_client = create_mock_http_client({seed_url: (200, html_content)})

    config = SeedURLCrawlerConfig(
        step=basic_crawl_step, job_id="test-job-relative", http_client=mock_client
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS
    assert result.total_urls_extracted == 3

    # All URLs should be absolute and normalized
    for extracted_url in result.extracted_urls:
        assert extracted_url.url.startswith("https://")
        assert "example.com" in extracted_url.url


# =============================================================================
# Cancellation Test Cases
# =============================================================================


@pytest.mark.asyncio
async def test_cancellation_before_seed_page_extraction(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test that cancellation is detected before seed page extraction."""
    seed_url = "https://example.com/products"

    html_content = b"""
    <html><body>
        <a class="product-link" href="/product/1">Product 1</a>
        <a class="product-link" href="/product/2">Product 2</a>
    </body></html>
    """

    mock_client = create_mock_http_client({seed_url: (200, html_content)})

    # Mock cancellation flag that returns cancelled immediately
    mock_flag = AsyncMock()
    mock_flag.is_cancelled.return_value = True

    config = SeedURLCrawlerConfig(
        step=basic_crawl_step,
        job_id="test-job-cancel-early",
        http_client=mock_client,
        cancellation_flag=mock_flag,
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.CANCELLED
    assert result.total_pages_crawled == 0
    assert result.total_urls_extracted == 0
    assert result.error_message == "Job was cancelled during execution"
    mock_flag.is_cancelled.assert_awaited()


@pytest.mark.asyncio
async def test_cancellation_during_pagination(
    seed_url_crawler: SeedURLCrawler,
    paginated_crawl_step: CrawlStep,
) -> None:
    """Test that cancellation is detected during pagination loop."""
    seed_url = "https://example.com/products?page=1"

    page1_content = b"""
    <html><body>
        <a class="product-link" href="/product/1">Product 1</a>
        <a class="product-link" href="/product/2">Product 2</a>
    </body></html>
    """

    page2_content = b"""
    <html><body>
        <a class="product-link" href="/product/3">Product 3</a>
        <a class="product-link" href="/product/4">Product 4</a>
    </body></html>
    """

    page3_content = b"""
    <html><body>
        <a class="product-link" href="/product/5">Product 5</a>
        <a class="product-link" href="/product/6">Product 6</a>
    </body></html>
    """

    def get_response(url: str) -> tuple[int, bytes]:
        if "page=1" in url:
            return (200, page1_content)
        elif "page=2" in url:
            return (200, page2_content)
        elif "page=3" in url:
            return (200, page3_content)
        else:
            return (404, b"Not Found")

    mock_client = create_mock_http_client(get_response)

    # Mock cancellation flag that returns cancelled after first page
    call_count = 0

    async def mock_is_cancelled(_job_id: str) -> bool:
        nonlocal call_count
        call_count += 1
        # Return cancelled after first check (during pagination)
        return call_count > 1

    mock_flag = AsyncMock()
    mock_flag.is_cancelled = mock_is_cancelled

    config = SeedURLCrawlerConfig(
        step=paginated_crawl_step,
        job_id="test-job-cancel-pagination",
        http_client=mock_client,
        cancellation_flag=mock_flag,
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.CANCELLED
    # Should have processed seed page before cancellation
    assert result.total_pages_crawled >= 1
    assert result.total_urls_extracted >= 2  # At least seed page URLs
    assert result.error_message == "Job was cancelled during execution"


@pytest.mark.asyncio
async def test_cancellation_preserves_partial_results(
    seed_url_crawler: SeedURLCrawler,
    paginated_crawl_step: CrawlStep,
) -> None:
    """Test that cancellation preserves partial results collected before cancellation."""
    seed_url = "https://example.com/products?page=1"

    page1_content = b"""
    <html><body>
        <a class="product-link" href="/product/1">Product 1</a>
        <a class="product-link" href="/product/2">Product 2</a>
    </body></html>
    """

    page2_content = b"""
    <html><body>
        <a class="product-link" href="/product/3">Product 3</a>
        <a class="product-link" href="/product/4">Product 4</a>
    </body></html>
    """

    page3_content = b"""
    <html><body>
        <a class="product-link" href="/product/5">Product 5</a>
        <a class="product-link" href="/product/6">Product 6</a>
    </body></html>
    """

    def get_response(url: str) -> tuple[int, bytes]:
        if "page=1" in url:
            return (200, page1_content)
        elif "page=2" in url:
            return (200, page2_content)
        elif "page=3" in url:
            return (200, page3_content)
        else:
            return (404, b"Not Found")

    mock_client = create_mock_http_client(get_response)

    # Mock cancellation flag that returns cancelled after 2 checks
    # Check 1: before seed page extraction (not cancelled)
    # Check 2: before page 2 processing (cancelled)
    call_count = 0

    async def mock_is_cancelled(_job_id: str) -> bool:
        nonlocal call_count
        call_count += 1
        return call_count >= 2

    mock_flag = AsyncMock()
    mock_flag.is_cancelled = mock_is_cancelled

    config = SeedURLCrawlerConfig(
        step=paginated_crawl_step,
        job_id="test-job-cancel-partial",
        http_client=mock_client,
        cancellation_flag=mock_flag,
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.CANCELLED
    assert result.total_pages_crawled >= 1
    # Should have extracted URLs from at least the seed page
    assert result.total_urls_extracted >= 2
    assert len(result.extracted_urls) >= 2
    # Verify URLs are actually preserved
    assert all(url.url.startswith("https://") for url in result.extracted_urls)


@pytest.mark.asyncio
async def test_no_cancellation_when_flag_not_provided(
    seed_url_crawler: SeedURLCrawler,
    basic_crawl_step: CrawlStep,
) -> None:
    """Test that crawl proceeds normally when no cancellation flag is provided."""
    seed_url = "https://example.com/products"

    html_content = b"""
    <html><body>
        <a class="product-link" href="/product/1">Product 1</a>
        <a class="product-link" href="/product/2">Product 2</a>
    </body></html>
    """

    mock_client = create_mock_http_client({seed_url: (200, html_content)})

    # No cancellation flag provided
    config = SeedURLCrawlerConfig(
        step=basic_crawl_step,
        job_id="test-job-no-cancel",
        http_client=mock_client,
    )
    result = await seed_url_crawler.crawl(seed_url, config)

    assert result.outcome == CrawlOutcome.SUCCESS
    assert result.total_pages_crawled == 1
    assert result.total_urls_extracted == 2
