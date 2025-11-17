"""Integration tests for PaginationService."""

import pytest
from urllib.parse import urlparse
from crawler.api.generated import PaginationConfig
from crawler.services.pagination import PaginationService


class TestPaginationService:
    """Tests for PaginationService integration."""

    def test_generate_urls_with_auto_detection_query_param(self) -> None:
        """Test URL generation with auto-detected query parameter pattern."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=10)

        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products?page=5", config=config
        )

        # Should generate seed URL + pages 6-10 (6 URLs total)
        assert len(urls) == 6
        assert urls[0] == "https://example.com/products?page=5"
        assert urls[-1] == "https://example.com/products?page=10"
        assert all("page=" in url for url in urls)

    def test_generate_urls_with_auto_detection_path_segment(self) -> None:
        """Test URL generation with auto-detected path segment pattern."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=8)

        urls = service.generate_pagination_urls(
            seed_url="https://example.com/page/3", config=config
        )

        # Should generate seed URL + pages 4-8 (6 URLs total)
        assert len(urls) == 6
        assert urls[0] == "https://example.com/page/3"
        assert urls[-1] == "https://example.com/page/8"

    def test_generate_urls_with_template(self) -> None:
        """Test URL generation with explicit template."""
        service = PaginationService()
        config = PaginationConfig(
            enabled=True,
            url_template="https://example.com/products?page={page}",
            start_page=1,
            max_pages=5,
        )

        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products?page=1", config=config
        )

        # Should generate pages 1-5 (seed + 4 more = 5 URLs)
        assert len(urls) == 5
        assert urls[0] == "https://example.com/products?page=1"
        assert urls[-1] == "https://example.com/products?page=5"

    def test_generate_urls_preserves_query_params(self) -> None:
        """Test that URL generation preserves other query parameters."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=3)

        urls = service.generate_pagination_urls(
            seed_url="https://example.com/search?q=test&category=tech&page=1",
            config=config,
        )

        assert len(urls) == 3  # Pages 1, 2, 3
        # All URLs should have q and category params
        for url in urls:
            assert "q=test" in url
            assert "category=tech" in url
            assert "page=" in url

    def test_generate_urls_from_arbitrary_start_page(self) -> None:
        """Test that pagination continues from arbitrary seed page."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=12)

        # Start from page 10
        urls = service.generate_pagination_urls(
            seed_url="https://example.com/articles?page=10", config=config
        )

        # Should generate pages 10, 11, 12 (3 URLs)
        assert len(urls) == 3
        assert "page=10" in urls[0]
        assert "page=11" in urls[1]
        assert "page=12" in urls[2]

    def test_generate_urls_disabled_pagination(self) -> None:
        """Test that disabled pagination returns only seed URL."""
        service = PaginationService()
        config = PaginationConfig(enabled=False)

        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products?page=5", config=config
        )

        assert len(urls) == 1
        assert urls[0] == "https://example.com/products?page=5"

    def test_generate_urls_no_pattern_detected(self) -> None:
        """Test behavior when no pagination pattern is detected."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=10)

        # URL with no detectable pagination pattern
        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products", config=config
        )

        # Should return only seed URL
        assert len(urls) == 1
        assert urls[0] == "https://example.com/products"

    def test_generate_urls_with_selector_fallback(self) -> None:
        """Test that selector-based config returns seed URL only."""
        service = PaginationService()
        config = PaginationConfig(
            enabled=True,
            type="next_button",
            selector="a.next-page",
            max_pages=10,
        )

        # No pattern in URL
        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products", config=config
        )

        # Should return only seed URL (selector-based handled separately)
        assert len(urls) == 1
        assert urls[0] == "https://example.com/products"

    def test_generate_urls_offset_based_pagination(self) -> None:
        """Test URL generation with offset-based pagination."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=5)

        # Start at offset=40 with limit=20 (page 3)
        urls = service.generate_pagination_urls(
            seed_url="https://example.com/api/items?offset=40&limit=20", config=config
        )

        # Should generate pages 3, 4, 5 (3 URLs)
        # Page 3 = offset 40, Page 4 = offset 60, Page 5 = offset 80
        assert len(urls) == 3
        assert "offset=40" in urls[0]  # Seed URL (page 3)
        assert "offset=60" in urls[1]  # Page 4
        assert "offset=80" in urls[2]  # Page 5

    def test_should_use_selector_based_pagination_with_pattern(self) -> None:
        """Test that selector-based is not used when pattern detected."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, selector="a.next", type="next_button")

        # URL has detectable pattern
        should_use_selector = service.should_use_selector_based_pagination(
            seed_url="https://example.com/products?page=5", config=config
        )

        assert should_use_selector is False  # Pattern detected, use URL generation

    def test_should_use_selector_based_pagination_no_pattern(self) -> None:
        """Test that selector-based is used when no pattern detected."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, selector="a.next", type="next_button")

        # URL has no detectable pattern
        should_use_selector = service.should_use_selector_based_pagination(
            seed_url="https://example.com/products", config=config
        )

        assert should_use_selector is True  # No pattern, must use selector

    def test_should_use_selector_based_pagination_with_template(self) -> None:
        """Test that selector-based is not used when template provided."""
        service = PaginationService()
        config = PaginationConfig(
            enabled=True,
            url_template="https://example.com/page/{page}",
            selector="a.next",
        )

        should_use_selector = service.should_use_selector_based_pagination(
            seed_url="https://example.com/products", config=config
        )

        assert should_use_selector is False  # Template provided, use it

    def test_get_pagination_strategy_disabled(self) -> None:
        """Test strategy detection when pagination disabled."""
        service = PaginationService()
        config = PaginationConfig(enabled=False)

        strategy = service.get_pagination_strategy(
            seed_url="https://example.com/products?page=5", config=config
        )

        assert strategy == "disabled"

    def test_get_pagination_strategy_template(self) -> None:
        """Test strategy detection with template."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, url_template="https://example.com/page/{page}")

        strategy = service.get_pagination_strategy(
            seed_url="https://example.com/products", config=config
        )

        assert strategy == "template"

    def test_get_pagination_strategy_auto_detected(self) -> None:
        """Test strategy detection with auto-detected pattern."""
        service = PaginationService()
        config = PaginationConfig(enabled=True)

        strategy = service.get_pagination_strategy(
            seed_url="https://example.com/products?page=5", config=config
        )

        assert strategy == "auto_detected"

    def test_get_pagination_strategy_selector(self) -> None:
        """Test strategy detection with selector fallback."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, selector="a.next")

        strategy = service.get_pagination_strategy(
            seed_url="https://example.com/products", config=config
        )

        assert strategy == "selector"


class TestPaginationServiceWithStopDetection:
    """Tests for PaginationService with stop detection (async)."""

    @pytest.mark.asyncio
    async def test_generate_with_stop_detection_success(self) -> None:
        """Test pagination with stop detection - normal completion."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=3)

        # Mock fetch function that returns successful responses
        async def mock_fetch(url: str) -> tuple[int, bytes]:
            content = f"Page content for {url}".encode() * 10  # >100 bytes
            return 200, content

        results = []
        async for url, status, content in service.generate_with_stop_detection(
            seed_url="https://example.com/page/1",
            config=config,
            fetch_fn=mock_fetch,
        ):
            results.append((url, status, len(content)))

        # Should crawl all 3 pages
        assert len(results) == 3
        assert all(status == 200 for _, status, _ in results)
        assert all(size > 100 for _, _, size in results)

    @pytest.mark.asyncio
    async def test_generate_with_stop_detection_404(self) -> None:
        """Test pagination stops on 404."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=5)

        call_count = 0

        async def mock_fetch(url: str) -> tuple[int, bytes]:
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # Different content for each page to avoid duplicate detection
                content = f"Page {call_count} content here. " * 10
                return 200, content.encode()
            else:
                return 404, b"Not Found"

        results = []
        async for url, status, content in service.generate_with_stop_detection(
            seed_url="https://example.com/page/1",
            config=config,
            fetch_fn=mock_fetch,
        ):
            results.append((url, status))

        # Should stop after 2 successful pages (3rd returns 404)
        assert len(results) == 2
        assert call_count == 3  # Fetched 3 times (2 success + 1 404)

    @pytest.mark.asyncio
    async def test_generate_with_stop_detection_duplicate_content(self) -> None:
        """Test pagination stops on duplicate content."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=5)

        # Same content for all pages (simulates end of pagination)
        same_content = b"Same page content here. " * 10

        async def mock_fetch(url: str) -> tuple[int, bytes]:
            return 200, same_content

        results = []
        async for url, status, content in service.generate_with_stop_detection(
            seed_url="https://example.com/page/1",
            config=config,
            fetch_fn=mock_fetch,
        ):
            results.append(url)

        # Should stop after first page (2nd has duplicate content)
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_generate_with_stop_detection_disabled(self) -> None:
        """Test that disabled pagination only fetches seed URL."""
        service = PaginationService()
        config = PaginationConfig(enabled=False)

        async def mock_fetch(url: str) -> tuple[int, bytes]:
            return 200, b"Content" * 20

        results = []
        async for url, status, content in service.generate_with_stop_detection(
            seed_url="https://example.com/products",
            config=config,
            fetch_fn=mock_fetch,
        ):
            results.append(url)

        # Should only fetch seed URL
        assert len(results) == 1
        assert results[0] == "https://example.com/products"

    @pytest.mark.asyncio
    async def test_generate_with_custom_stop_detection_params(self) -> None:
        """Test pagination with custom stop detection parameters."""
        service = PaginationService()
        # Configure custom stop detection: higher empty threshold, no content hashing
        config = PaginationConfig(
            enabled=True,
            max_pages=10,
            min_content_length=50,  # Custom: lower threshold
            max_empty_responses=3,  # Custom: allow 3 empty responses
            track_content_hashes=False,  # Custom: disable duplicate detection
            track_urls=True,  # Keep URL tracking enabled
        )

        call_count = 0

        async def mock_fetch(url: str) -> tuple[int, bytes]:
            nonlocal call_count
            call_count += 1
            # Return same content (would trigger duplicate if enabled)
            return 200, b"x" * 60  # >50 bytes (meets custom min_content_length)

        results = []
        async for url, status, content in service.generate_with_stop_detection(
            seed_url="https://example.com/page/1",
            config=config,
            fetch_fn=mock_fetch,
        ):
            results.append(url)

        # Should crawl all 10 pages despite duplicate content (track_content_hashes=False)
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_generate_with_custom_empty_threshold(self) -> None:
        """Test custom max_empty_responses parameter."""
        service = PaginationService()
        # Allow 3 consecutive empty responses before stopping
        config = PaginationConfig(
            enabled=True,
            max_pages=10,
            min_content_length=100,
            max_empty_responses=3,  # Custom: allow 3 empty
            track_content_hashes=False,  # Disable to isolate empty test
        )

        call_count = 0

        async def mock_fetch(url: str) -> tuple[int, bytes]:
            nonlocal call_count
            call_count += 1
            # Return empty content
            return 200, b"small"  # <100 bytes = empty

        results = []
        async for url, status, content in service.generate_with_stop_detection(
            seed_url="https://example.com/page/1",
            config=config,
            fetch_fn=mock_fetch,
        ):
            results.append(url)

        # Should yield 2 pages before stopping (stops on 3rd empty response)
        assert len(results) == 2
        assert call_count == 3  # Fetched 3 times, stopped on 3rd

    @pytest.mark.asyncio
    async def test_generate_with_custom_min_content_length(self) -> None:
        """Test custom min_content_length parameter."""
        service = PaginationService()
        # Set very high minimum content length
        config = PaginationConfig(
            enabled=True,
            max_pages=5,
            min_content_length=500,  # Custom: very high threshold
            max_empty_responses=2,
            track_content_hashes=False,
        )

        call_count = 0

        async def mock_fetch(url: str) -> tuple[int, bytes]:
            nonlocal call_count
            call_count += 1
            # Return content that's "empty" by custom threshold
            return 200, b"x" * 200  # 200 bytes < 500 bytes = empty

        results = []
        async for url, status, content in service.generate_with_stop_detection(
            seed_url="https://example.com/page/1",
            config=config,
            fetch_fn=mock_fetch,
        ):
            results.append(url)

        # Should yield 1 page before stopping (stops on 2nd "empty" response)
        # 200 bytes < 500 threshold = empty
        assert len(results) == 1
        assert call_count == 2  # Fetched 2 times, stopped on 2nd


class TestPaginationServiceEdgeCases:
    """Edge case tests for PaginationService."""

    def test_generate_urls_max_pages_equals_start_page(self) -> None:
        """Test when max_pages equals the start page."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=5)

        # Start at page 5, max is also 5
        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products?page=5", config=config
        )

        # Should return only seed URL (already at max)
        assert len(urls) == 1
        assert "page=5" in urls[0]

    def test_generate_urls_start_page_beyond_max(self) -> None:
        """Test when start page is beyond max_pages."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=3)

        # Start at page 10, max is 3
        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products?page=10", config=config
        )

        # Should return only seed URL (already beyond max)
        assert len(urls) == 1
        assert "page=10" in urls[0]

    def test_generate_urls_with_fragment(self) -> None:
        """Test URL generation preserves fragments."""
        service = PaginationService()
        config = PaginationConfig(enabled=True, max_pages=3)

        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products?page=1#section", config=config
        )

        # Fragments should be preserved
        assert len(urls) == 3
        assert all("#section" in url for url in urls)

    def test_generate_urls_multiple_strategies(self) -> None:
        """Test that template takes priority over auto-detection."""
        service = PaginationService()
        config = PaginationConfig(
            enabled=True,
            url_template="https://custom.com/p/{page}",
            max_pages=3,
        )

        # Seed URL has detectable pattern, but template should be used
        urls = service.generate_pagination_urls(
            seed_url="https://example.com/products?page=5", config=config
        )

        # Should use template, not detected pattern
        assert len(urls) == 3
        assert all(urlparse(url).hostname == "custom.com" for url in urls)
        assert all("/p/" in url for url in urls)
