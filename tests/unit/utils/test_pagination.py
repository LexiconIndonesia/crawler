"""Unit tests for pagination utilities."""

import pytest

from crawler.utils.pagination import (
    PaginationPatternDetector,
    PaginationStopDetector,
    PaginationURLGenerator,
    PathEmbeddedPattern,
    PathSegmentPattern,
    QueryParamPattern,
    TemplatePattern,
)

# =============================================================================
# QueryParamPattern Tests
# =============================================================================


class TestQueryParamPattern:
    """Tests for query parameter pagination pattern."""

    def test_simple_page_parameter(self):
        """Test simple ?page=N pattern."""
        pattern = QueryParamPattern(param_name="page", current_page=5)
        url = pattern.generate_url("https://example.com/products?page=5", 6)
        assert url == "https://example.com/products?page=6"

    def test_page_with_multiple_params(self):
        """Test page parameter with other query parameters."""
        pattern = QueryParamPattern(param_name="page", current_page=2)
        url = pattern.generate_url(
            "https://example.com/search?q=test&page=2&sort=date", 3
        )
        assert "page=3" in url
        assert "q=test" in url
        assert "sort=date" in url

    def test_offset_based_pagination(self):
        """Test offset-based pagination."""
        pattern = QueryParamPattern(param_name="offset", current_page=3, increment=20)
        # Page 3 with increment 20 = offset 40
        url = pattern.generate_url("https://example.com/api/items?offset=40&limit=20", 4)
        assert "offset=60" in url  # Page 4 = offset 60
        assert "limit=20" in url

    def test_custom_page_param_name(self):
        """Test custom page parameter name."""
        pattern = QueryParamPattern(param_name="p", current_page=1)
        url = pattern.generate_url("https://example.com/list?p=1", 2)
        assert "p=2" in url

    def test_preserves_fragment(self):
        """Test that URL fragments are preserved."""
        pattern = QueryParamPattern(param_name="page", current_page=1)
        url = pattern.generate_url("https://example.com/page?page=1#section", 2)
        assert url == "https://example.com/page?page=2#section"


# =============================================================================
# PathSegmentPattern Tests
# =============================================================================


class TestPathSegmentPattern:
    """Tests for path segment pagination pattern."""

    def test_simple_path_segment(self):
        """Test /page/N pattern."""
        pattern = PathSegmentPattern(segment_index=2, current_page=5)
        url = pattern.generate_url("https://example.com/page/5", 6)
        assert url == "https://example.com/page/6"

    def test_nested_path_segment(self):
        """Test /category/products/page/N pattern."""
        pattern = PathSegmentPattern(segment_index=4, current_page=3)
        url = pattern.generate_url("https://example.com/category/products/page/3", 4)
        assert url == "https://example.com/category/products/page/4"

    def test_short_path_segment(self):
        """Test /p/N pattern."""
        pattern = PathSegmentPattern(segment_index=2, current_page=1)
        url = pattern.generate_url("https://example.com/p/1", 2)
        assert url == "https://example.com/p/2"

    def test_preserves_query_params(self):
        """Test that query parameters are preserved."""
        pattern = PathSegmentPattern(segment_index=2, current_page=5)
        url = pattern.generate_url("https://example.com/page/5?sort=date", 6)
        assert url == "https://example.com/page/6?sort=date"


# =============================================================================
# PathEmbeddedPattern Tests
# =============================================================================


class TestPathEmbeddedPattern:
    """Tests for embedded path pagination pattern."""

    def test_embedded_number_with_prefix(self):
        """Test /products-p5 pattern."""
        pattern = PathEmbeddedPattern(prefix="/products-p", current_page=5, suffix="")
        url = pattern.generate_url("https://example.com/products-p5", 6)
        assert url == "https://example.com/products-p6"

    def test_embedded_number_with_suffix(self):
        """Test /list5.html pattern."""
        pattern = PathEmbeddedPattern(prefix="/list", current_page=5, suffix=".html")
        url = pattern.generate_url("https://example.com/list5.html", 6)
        assert url == "https://example.com/list6.html"

    def test_complex_embedded_pattern(self):
        """Test /archive2024-page3 pattern."""
        pattern = PathEmbeddedPattern(
            prefix="/archive2024-page", current_page=3, suffix=""
        )
        url = pattern.generate_url("https://example.com/archive2024-page3", 4)
        assert url == "https://example.com/archive2024-page4"


# =============================================================================
# TemplatePattern Tests
# =============================================================================


class TestTemplatePattern:
    """Tests for template-based pagination pattern."""

    def test_simple_template(self):
        """Test simple {page} template."""
        pattern = TemplatePattern(
            current_page=1, template="https://example.com/page/{page}"
        )
        url = pattern.generate_url("", 5)
        assert url == "https://example.com/page/5"

    def test_template_with_query_params(self):
        """Test template with other parameters."""
        pattern = TemplatePattern(
            current_page=1,
            template="https://example.com/search?q=test&page={page}&sort=date",
        )
        url = pattern.generate_url("", 3)
        assert url == "https://example.com/search?q=test&page=3&sort=date"

    def test_template_in_path(self):
        """Test template in path segment."""
        pattern = TemplatePattern(
            current_page=1, template="https://example.com/category/{page}/items"
        )
        url = pattern.generate_url("", 2)
        assert url == "https://example.com/category/2/items"


# =============================================================================
# PaginationPatternDetector Tests
# =============================================================================


class TestPaginationPatternDetector:
    """Tests for pagination pattern detection."""

    def test_detect_query_param_page(self):
        """Test detection of ?page=N pattern."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/products?page=5")

        assert isinstance(pattern, QueryParamPattern)
        assert pattern.param_name == "page"
        assert pattern.current_page == 5

    def test_detect_query_param_p(self):
        """Test detection of ?p=N pattern."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/list?p=3&sort=date")

        assert isinstance(pattern, QueryParamPattern)
        assert pattern.param_name == "p"
        assert pattern.current_page == 3

    def test_detect_offset_based(self):
        """Test detection of offset-based pagination."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/api/items?offset=40&limit=20")

        assert isinstance(pattern, QueryParamPattern)
        assert pattern.param_name == "offset"
        assert pattern.current_page == 3  # offset 40 / limit 20 = page 3
        assert pattern.increment == 20

    def test_detect_path_segment_page(self):
        """Test detection of /page/N pattern."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/page/5")

        assert isinstance(pattern, PathSegmentPattern)
        assert pattern.segment_index == 2
        assert pattern.current_page == 5

    def test_detect_path_segment_nested(self):
        """Test detection of nested /page/N pattern."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/category/products/page/3")

        assert isinstance(pattern, PathSegmentPattern)
        assert pattern.segment_index == 4
        assert pattern.current_page == 3

    def test_detect_embedded_pattern(self):
        """Test detection of embedded number pattern."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/products-p5")

        assert isinstance(pattern, PathEmbeddedPattern)
        assert pattern.prefix == "/products-p"
        assert pattern.current_page == 5
        assert pattern.suffix == ""

    def test_detect_embedded_with_extension(self):
        """Test detection of embedded pattern with file extension."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/list5.html")

        assert isinstance(pattern, PathEmbeddedPattern)
        assert pattern.prefix == "/list"
        assert pattern.current_page == 5
        assert pattern.suffix == ".html"

    def test_no_pattern_detected(self):
        """Test when no pagination pattern is found."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/products")

        assert pattern is None

    def test_priority_query_over_path(self):
        """Test that query params take priority over path patterns."""
        detector = PaginationPatternDetector()
        # URL has both query param and path segment
        pattern = detector.detect("https://example.com/page/10?page=5")

        # Query param should win
        assert isinstance(pattern, QueryParamPattern)
        assert pattern.current_page == 5

    def test_invalid_url_raises_error(self):
        """Test that invalid URLs raise ValueError."""
        detector = PaginationPatternDetector()

        with pytest.raises(ValueError, match="URL must have scheme and hostname"):
            detector.detect("not-a-url")

        with pytest.raises(ValueError, match="must be a non-empty string"):
            detector.detect("")

    def test_detect_with_fragment(self):
        """Test detection works with URL fragments."""
        detector = PaginationPatternDetector()
        pattern = detector.detect("https://example.com/products?page=5#section")

        assert isinstance(pattern, QueryParamPattern)
        assert pattern.current_page == 5


# =============================================================================
# PaginationURLGenerator Tests
# =============================================================================


class TestPaginationURLGenerator:
    """Tests for pagination URL generator."""

    def test_next_url_query_param(self):
        """Test generating next URL with query param pattern."""
        pattern = QueryParamPattern(param_name="page", current_page=5)
        generator = PaginationURLGenerator(
            "https://example.com/products?page=5", pattern, max_pages=100
        )

        url = generator.next_url()
        assert url == "https://example.com/products?page=6"
        assert generator.current_page == 6

    def test_next_url_max_pages_reached(self):
        """Test that next_url returns None when max_pages reached."""
        pattern = QueryParamPattern(param_name="page", current_page=99)
        generator = PaginationURLGenerator(
            "https://example.com/products?page=99", pattern, max_pages=100
        )

        url1 = generator.next_url()
        assert url1 == "https://example.com/products?page=100"

        url2 = generator.next_url()
        assert url2 is None  # Max pages reached

    def test_generate_range(self):
        """Test generating a range of URLs."""
        pattern = QueryParamPattern(param_name="page", current_page=5)
        generator = PaginationURLGenerator(
            "https://example.com/products?page=5", pattern, max_pages=100
        )

        urls = generator.generate_range(6, 10)
        assert len(urls) == 5
        assert urls[0] == "https://example.com/products?page=6"
        assert urls[-1] == "https://example.com/products?page=10"

    def test_generate_range_respects_max_pages(self):
        """Test that generate_range respects max_pages limit."""
        pattern = QueryParamPattern(param_name="page", current_page=5)
        generator = PaginationURLGenerator(
            "https://example.com/products?page=5", pattern, max_pages=10
        )

        urls = generator.generate_range(6, 20)  # Request beyond max
        assert len(urls) == 5  # Only 6-10 (5 URLs)
        assert urls[-1] == "https://example.com/products?page=10"

    def test_generate_all(self):
        """Test generating all remaining URLs."""
        pattern = QueryParamPattern(param_name="page", current_page=5)
        generator = PaginationURLGenerator(
            "https://example.com/products?page=5", pattern, max_pages=8
        )

        urls = generator.generate_all()
        assert len(urls) == 3  # Pages 6, 7, 8
        assert urls[0] == "https://example.com/products?page=6"
        assert urls[-1] == "https://example.com/products?page=8"


# =============================================================================
# PaginationStopDetector Tests
# =============================================================================


class TestPaginationStopDetector:
    """Tests for pagination stop detection."""

    def test_404_stops_pagination(self):
        """Test that 404 status stops pagination."""
        detector = PaginationStopDetector()
        result = detector.check_response(404, b"Not Found", "https://example.com/page/100")

        assert result.should_stop is True
        assert "404" in result.reason

    def test_403_stops_pagination(self):
        """Test that 403 status stops pagination."""
        detector = PaginationStopDetector()
        result = detector.check_response(403, b"Forbidden", "https://example.com/page/5")

        assert result.should_stop is True
        assert "403" in result.reason

    def test_500_stops_pagination(self):
        """Test that 5xx status stops pagination."""
        detector = PaginationStopDetector()
        result = detector.check_response(500, b"Server Error", "https://example.com/page/5")

        assert result.should_stop is True
        assert "500" in result.reason

    def test_empty_content_stops_after_threshold(self):
        """Test that consecutive empty responses stop pagination."""
        detector = PaginationStopDetector(
            min_content_length=100, max_empty_responses=2
        )

        # First empty response
        result1 = detector.check_response(200, b"", "https://example.com/page/1")
        assert result1.should_stop is False

        # Second empty response - should stop
        result2 = detector.check_response(200, b"", "https://example.com/page/2")
        assert result2.should_stop is True
        assert "empty" in result2.reason.lower()

    def test_empty_content_resets_on_valid_response(self):
        """Test that empty counter resets with valid content."""
        detector = PaginationStopDetector(
            min_content_length=100, max_empty_responses=2
        )

        # Empty response
        detector.check_response(200, b"", "https://example.com/page/1")

        # Valid response - resets counter
        detector.check_response(200, b"x" * 200, "https://example.com/page/2")

        # Another empty response - should not stop (counter was reset)
        result = detector.check_response(200, b"", "https://example.com/page/3")
        assert result.should_stop is False

    def test_duplicate_content_detected(self):
        """Test duplicate content detection via hashing."""
        detector = PaginationStopDetector(track_content_hashes=True)

        # Use content > 100 bytes to avoid empty content detection
        content = b"Same content on multiple pages. " * 10  # 320 bytes

        # First occurrence
        result1 = detector.check_response(200, content, "https://example.com/page/1")
        assert result1.should_stop is False

        # Duplicate content - should stop
        result2 = detector.check_response(200, content, "https://example.com/page/2")
        assert result2.should_stop is True
        assert "duplicate" in result2.reason.lower()

    def test_duplicate_content_tracking_disabled(self):
        """Test that duplicate detection can be disabled."""
        detector = PaginationStopDetector(track_content_hashes=False)

        # Use content > 100 bytes to avoid empty content detection
        content = b"Same content on multiple pages. " * 10  # 320 bytes

        result1 = detector.check_response(200, content, "https://example.com/page/1")
        result2 = detector.check_response(200, content, "https://example.com/page/2")

        # Should not stop when tracking disabled
        assert result1.should_stop is False
        assert result2.should_stop is False

    def test_circular_pagination_detected(self):
        """Test circular pagination (URL revisit) detection."""
        detector = PaginationStopDetector(track_urls=True)

        # First visit
        result1 = detector.check_response(
            200, b"content", "https://example.com/page/1"
        )
        assert result1.should_stop is False

        # Revisit same URL - should stop
        result2 = detector.check_response(
            200, b"different content", "https://example.com/page/1"
        )
        assert result2.should_stop is True
        assert "circular" in result2.reason.lower()

    def test_url_tracking_disabled(self):
        """Test that URL tracking can be disabled."""
        # Disable both URL and content tracking to isolate the test
        detector = PaginationStopDetector(track_urls=False, track_content_hashes=False)

        url = "https://example.com/page/1"
        # Use content > 100 bytes to avoid empty content detection
        content = b"Page content here. " * 10  # 190 bytes
        result1 = detector.check_response(200, content, url)
        result2 = detector.check_response(200, content, url)

        # Should not stop when tracking disabled
        assert result1.should_stop is False
        assert result2.should_stop is False

    def test_reset_clears_state(self):
        """Test that reset clears detector state."""
        detector = PaginationStopDetector()

        # Add some state
        detector.check_response(200, b"content", "https://example.com/page/1")
        detector.check_response(200, b"", "https://example.com/page/2")

        # Reset
        detector.reset()

        # State should be cleared
        assert len(detector.visited_hashes) == 0
        assert len(detector.visited_urls) == 0
        assert detector.consecutive_empty == 0

    def test_string_content_accepted(self):
        """Test that string content is handled properly."""
        detector = PaginationStopDetector()

        result = detector.check_response(200, "String content", "https://example.com/page/1")
        assert result.should_stop is False


# =============================================================================
# Integration Tests
# =============================================================================


class TestPaginationIntegration:
    """Integration tests combining detector and generator."""

    def test_detect_and_generate_query_param(self):
        """Test full workflow: detect pattern and generate URLs."""
        seed_url = "https://example.com/products?category=tech&page=5&sort=date"

        # Detect pattern
        detector = PaginationPatternDetector()
        pattern = detector.detect(seed_url)

        assert pattern is not None
        assert isinstance(pattern, QueryParamPattern)

        # Generate URLs
        generator = PaginationURLGenerator(seed_url, pattern, max_pages=10)
        urls = generator.generate_range(6, 8)

        assert len(urls) == 3
        assert all("page=" in url for url in urls)
        assert all("category=tech" in url for url in urls)
        assert all("sort=date" in url for url in urls)

    def test_detect_and_generate_path_segment(self):
        """Test full workflow with path segment pattern."""
        seed_url = "https://example.com/category/electronics/page/3"

        detector = PaginationPatternDetector()
        pattern = detector.detect(seed_url)

        assert isinstance(pattern, PathSegmentPattern)

        generator = PaginationURLGenerator(seed_url, pattern, max_pages=10)
        next_url = generator.next_url()

        assert next_url == "https://example.com/category/electronics/page/4"

    def test_from_arbitrary_seed_page(self):
        """Test that pagination continues from arbitrary seed page."""
        # User starts from page 10, not page 1
        seed_url = "https://example.com/articles?page=10"

        detector = PaginationPatternDetector()
        pattern = detector.detect(seed_url)

        assert pattern.current_page == 10

        generator = PaginationURLGenerator(seed_url, pattern, max_pages=15)
        urls = generator.generate_all()

        # Should generate pages 11-15 (5 URLs)
        assert len(urls) == 5
        assert "page=11" in urls[0]
        assert "page=15" in urls[-1]
