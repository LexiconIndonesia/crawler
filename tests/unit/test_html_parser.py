"""Unit tests for HTML parser service."""

import pytest

from crawler.services.html_parser import HTMLParserService


@pytest.fixture
def html_parser() -> HTMLParserService:
    """Create HTML parser service instance."""
    return HTMLParserService()


@pytest.fixture
def sample_html() -> str:
    """Sample HTML for testing."""
    return """
    <html>
        <head><title>Test Page</title></head>
        <body>
            <div class="container">
                <h1>Article List</h1>
                <article class="article" data-url="/article/1">
                    <h3 class="article-title">First Article</h3>
                    <p class="article-preview">This is the first article preview</p>
                    <a href="/article/1" class="article-link">Read more</a>
                </article>
                <article class="article" data-url="/article/2">
                    <h3 class="article-title">Second Article</h3>
                    <p class="article-preview">This is the second article preview</p>
                    <a href="/article/2" class="article-link">Read more</a>
                </article>
                <article class="article">
                    <h3 class="article-title">Third Article</h3>
                    <p class="article-preview">This is the third article preview</p>
                    <a href="https://external.com/article" class="external-link">External</a>
                </article>
            </div>
            <nav>
                <a href="/page/1" class="nav-link">Page 1</a>
                <a href="/page/2" class="nav-link">Page 2</a>
            </nav>
        </body>
    </html>
    """


class TestHTMLParserService:
    """Test cases for HTMLParserService."""

    def test_parse_html_success(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test successful HTML parsing."""
        soup = html_parser.parse_html(sample_html)
        assert soup is not None
        assert soup.find("h1").text == "Article List"

    def test_parse_html_bytes(self, html_parser: HTMLParserService) -> None:
        """Test parsing HTML from bytes."""
        html_bytes = b"<html><body><h1>Test</h1></body></html>"
        soup = html_parser.parse_html(html_bytes)
        assert soup is not None
        assert soup.find("h1").text == "Test"

    def test_parse_html_empty_content(self, html_parser: HTMLParserService) -> None:
        """Test parsing empty content raises error."""
        with pytest.raises(ValueError, match="HTML content cannot be empty"):
            html_parser.parse_html("")

    def test_apply_css_selector_single(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test applying CSS selector to get single result."""
        soup = html_parser.parse_html(sample_html)
        results = html_parser.apply_css_selector(soup, "h1", select_all=False)
        assert len(results) == 1
        assert results[0] == "Article List"

    def test_apply_css_selector_multiple(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test applying CSS selector to get multiple results."""
        soup = html_parser.parse_html(sample_html)
        results = html_parser.apply_css_selector(
            soup, ".article-title", attribute=None, select_all=True
        )
        assert len(results) == 3
        assert "First Article" in results
        assert "Second Article" in results
        assert "Third Article" in results

    def test_apply_css_selector_attribute(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting attribute values with CSS selector."""
        soup = html_parser.parse_html(sample_html)
        results = html_parser.apply_css_selector(
            soup, ".article-link", attribute="href", select_all=True
        )
        assert len(results) == 2
        assert "/article/1" in results
        assert "/article/2" in results

    def test_apply_css_selector_no_match(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test CSS selector with no matches returns empty list."""
        soup = html_parser.parse_html(sample_html)
        results = html_parser.apply_css_selector(soup, ".nonexistent", select_all=True)
        assert results == []

    def test_apply_xpath_text(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test applying XPath to extract text."""
        results = html_parser.apply_xpath(sample_html, "//h1", attribute=None)
        assert len(results) == 1
        assert results[0] == "Article List"

    def test_apply_xpath_attribute(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test applying XPath to extract attribute."""
        results = html_parser.apply_xpath(
            sample_html, "//a[@class='article-link']", attribute="href"
        )
        assert len(results) == 2
        assert "/article/1" in results
        assert "/article/2" in results

    def test_apply_xpath_multiple(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test applying XPath to get multiple results."""
        results = html_parser.apply_xpath(sample_html, "//h3[@class='article-title']")
        assert len(results) == 3

    def test_apply_xpath_no_match(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test XPath with no matches returns empty list."""
        results = html_parser.apply_xpath(sample_html, "//nonexistent")
        assert results == []

    def test_extract_data_css_single(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting single result with CSS."""
        result = html_parser.extract_data(
            sample_html, "h1", attribute=None, selector_type="css", result_type="single"
        )
        assert result == "Article List"

    def test_extract_data_css_array(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test extracting array result with CSS."""
        results = html_parser.extract_data(
            sample_html,
            ".article-link",
            attribute="href",
            selector_type="css",
            result_type="array",
        )
        assert isinstance(results, list)
        assert len(results) == 2
        assert "/article/1" in results

    def test_extract_data_xpath_single(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting single result with XPath."""
        result = html_parser.extract_data(
            sample_html, "//h1", attribute=None, selector_type="xpath", result_type="single"
        )
        assert result == "Article List"

    def test_extract_data_xpath_array(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting array result with XPath."""
        results = html_parser.extract_data(
            sample_html,
            "//a[@class='article-link']",
            attribute="href",
            selector_type="xpath",
            result_type="array",
        )
        assert isinstance(results, list)
        assert len(results) == 2

    def test_extract_data_no_match_single(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting single result with no match returns None."""
        result = html_parser.extract_data(
            sample_html, ".nonexistent", attribute=None, result_type="single"
        )
        assert result is None

    def test_extract_data_no_match_array(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting array result with no match returns empty list."""
        results = html_parser.extract_data(
            sample_html, ".nonexistent", attribute=None, result_type="array"
        )
        assert results == []

    def test_resolve_relative_url_root(self, html_parser: HTMLParserService) -> None:
        """Test resolving root-relative URL."""
        result = html_parser.resolve_relative_url("/article/1", "https://example.com/page")
        assert result == "https://example.com/article/1"

    def test_resolve_relative_url_path(self, html_parser: HTMLParserService) -> None:
        """Test resolving path-relative URL."""
        result = html_parser.resolve_relative_url("article/1", "https://example.com/news/")
        assert result == "https://example.com/news/article/1"

    def test_resolve_relative_url_absolute(self, html_parser: HTMLParserService) -> None:
        """Test resolving already-absolute URL."""
        result = html_parser.resolve_relative_url(
            "https://other.com/article", "https://example.com"
        )
        assert result == "https://other.com/article"

    def test_resolve_relative_url_protocol(self, html_parser: HTMLParserService) -> None:
        """Test resolving protocol-relative URL."""
        result = html_parser.resolve_relative_url(
            "//cdn.example.com/image.jpg", "https://example.com"
        )
        assert result == "https://cdn.example.com/image.jpg"

    def test_extract_data_attribute(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test extracting data attributes."""
        results = html_parser.extract_data(
            sample_html,
            ".article",
            attribute="data-url",
            selector_type="css",
            result_type="array",
        )
        assert len(results) == 2  # Only first two articles have data-url
        assert "/article/1" in results
        assert "/article/2" in results

    def test_extract_url_metadata(self, html_parser: HTMLParserService, sample_html: str) -> None:
        """Test extracting URL metadata from link element."""
        soup = html_parser.parse_html(sample_html)
        link = soup.select_one(".article-link")

        metadata = html_parser.extract_url_metadata(
            soup, link, metadata_fields={"title": ".article-title", "preview": ".article-preview"}
        )

        assert metadata is not None
        # When metadata_fields are provided, they override the default
        # In this case, .article-title selector finds "First Article"
        assert metadata["title"] == "First Article"
        assert metadata["preview"] == "This is the first article preview"

    def test_extract_url_metadata_no_fields(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting metadata without custom fields."""
        soup = html_parser.parse_html(sample_html)
        link = soup.select_one(".article-link")

        metadata = html_parser.extract_url_metadata(soup, link, metadata_fields=None)

        assert metadata is not None
        assert metadata["title"] == "Read more"  # From link text
        assert metadata["preview"] is None

    def test_extract_url_metadata_none_element(
        self, html_parser: HTMLParserService, sample_html: str
    ) -> None:
        """Test extracting metadata with None element."""
        soup = html_parser.parse_html(sample_html)

        metadata = html_parser.extract_url_metadata(soup, None, metadata_fields=None)

        assert metadata is not None
        assert metadata["title"] is None
        assert metadata["preview"] is None
