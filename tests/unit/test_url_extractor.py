"""Unit tests for URL extractor service."""

from unittest.mock import AsyncMock

import pytest

from crawler.api.generated import SelectorConfig
from crawler.services.html_parser import HTMLParserService
from crawler.services.redis_cache import URLDeduplicationCache
from crawler.services.url_extractor import ExtractedURL, URLExtractorService


@pytest.fixture
def html_parser() -> HTMLParserService:
    """Create HTML parser service instance."""
    return HTMLParserService()


@pytest.fixture
def mock_dedup_cache() -> AsyncMock:
    """Create mock deduplication cache."""
    cache = AsyncMock(spec=URLDeduplicationCache)
    cache.exists = AsyncMock(return_value=False)
    cache.set = AsyncMock(return_value=True)
    return cache


@pytest.fixture
def url_extractor(html_parser: HTMLParserService) -> URLExtractorService:
    """Create URL extractor service without dedup cache."""
    return URLExtractorService(html_parser=html_parser, dedup_cache=None)


@pytest.fixture
def url_extractor_with_cache(
    html_parser: HTMLParserService, mock_dedup_cache: AsyncMock
) -> URLExtractorService:
    """Create URL extractor service with mock dedup cache."""
    return URLExtractorService(html_parser=html_parser, dedup_cache=mock_dedup_cache)


@pytest.fixture
def sample_list_html() -> str:
    """Sample list page HTML."""
    return """
    <html>
        <body>
            <div class="article-list">
                <article>
                    <h3 class="title">First Article</h3>
                    <p class="preview">Preview of first article</p>
                    <a href="/article/1" class="article-link">Read more</a>
                </article>
                <article>
                    <h3 class="title">Second Article</h3>
                    <p class="preview">Preview of second article</p>
                    <a href="/article/2" class="article-link">Read more</a>
                </article>
                <article>
                    <h3 class="title">Third Article</h3>
                    <p class="preview">Preview of third article</p>
                    <a href="https://example.com/article/3" class="article-link">Read more</a>
                </article>
                <!-- Relative URL without leading slash -->
                <article>
                    <h3 class="title">Fourth Article</h3>
                    <a href="article/4" class="article-link">Read more</a>
                </article>
            </div>
        </body>
    </html>
    """


@pytest.fixture
def data_attribute_html() -> str:
    """HTML with URLs in data attributes."""
    return """
    <html>
        <body>
            <div class="article-list">
                <div class="article" data-url="/article/1">
                    <h3>Article One</h3>
                </div>
                <div class="article" data-url="/article/2">
                    <h3>Article Two</h3>
                </div>
                <div class="article" data-href="https://example.com/article/3">
                    <h3>Article Three</h3>
                </div>
            </div>
        </body>
    </html>
    """


class TestURLExtractorService:
    """Test cases for URLExtractorService."""

    async def test_extract_urls_simple_string_selector(
        self, url_extractor: URLExtractorService, sample_list_html: str
    ) -> None:
        """Test extracting URLs with simple string selector."""
        results = await url_extractor.extract_urls(
            html_content=sample_list_html,
            base_url="https://example.com",
            url_selector="a.article-link",
            deduplicate=False,
        )

        assert len(results) == 4
        assert all(isinstance(url, ExtractedURL) for url in results)

        # Check normalized URLs
        urls = [url.normalized_url for url in results]
        assert "https://example.com/article/1" in urls
        assert "https://example.com/article/2" in urls
        assert "https://example.com/article/3" in urls
        assert "https://example.com/article/4" in urls

    async def test_extract_urls_selector_config(
        self, url_extractor: URLExtractorService, sample_list_html: str
    ) -> None:
        """Test extracting URLs with SelectorConfig."""
        config = SelectorConfig(selector="a.article-link", attribute="href", type="array")

        results = await url_extractor.extract_urls(
            html_content=sample_list_html,
            base_url="https://example.com",
            url_selector=config,
            deduplicate=False,
        )

        assert len(results) == 4

    async def test_extract_urls_with_metadata(
        self, url_extractor: URLExtractorService, sample_list_html: str
    ) -> None:
        """Test extracting URLs with metadata selectors."""
        results = await url_extractor.extract_urls(
            html_content=sample_list_html,
            base_url="https://example.com",
            url_selector="a.article-link",
            metadata_selectors={"title": ".title", "preview": ".preview"},
            deduplicate=False,
        )

        assert len(results) == 4

        # First URL should have metadata
        first = results[0]
        assert first.metadata is not None
        assert "title" in first.metadata
        assert "preview" in first.metadata

    async def test_extract_urls_relative_urls(
        self, url_extractor: URLExtractorService, sample_list_html: str
    ) -> None:
        """Test resolving relative URLs correctly."""
        results = await url_extractor.extract_urls(
            html_content=sample_list_html,
            base_url="https://example.com/news/",
            url_selector="a.article-link",
            deduplicate=False,
        )

        assert len(results) == 4

        # Find the relative URL (article/4)
        relative_url = next((url for url in results if "/article/4" in url.normalized_url), None)
        assert relative_url is not None
        # Should be resolved relative to base URL
        assert relative_url.normalized_url == "https://example.com/news/article/4"

    async def test_extract_urls_deduplication_within_extraction(
        self, url_extractor: URLExtractorService
    ) -> None:
        """Test deduplication within single extraction."""
        html = """
        <html><body>
            <a href="/article/1" class="link">Link 1</a>
            <a href="/article/1" class="link">Link 1 Duplicate</a>
            <a href="/article/1?utm_source=fb" class="link">Link 1 with tracking</a>
            <a href="/article/2" class="link">Link 2</a>
        </body></html>
        """

        results = await url_extractor.extract_urls(
            html_content=html,
            base_url="https://example.com",
            url_selector="a.link",
            deduplicate=True,
        )

        # Should only have 2 unique URLs (article/1 and article/2)
        assert len(results) == 2
        urls = [url.normalized_url for url in results]
        assert "https://example.com/article/1" in urls
        assert "https://example.com/article/2" in urls

    async def test_extract_urls_with_cache_deduplication(
        self, url_extractor_with_cache: URLExtractorService, sample_list_html: str
    ) -> None:
        """Test deduplication using cache."""
        # First extraction
        results = await url_extractor_with_cache.extract_urls(
            html_content=sample_list_html,
            base_url="https://example.com",
            url_selector="a.article-link",
            deduplicate=True,
            job_id="job-123",
        )

        assert len(results) == 4

        # Batch check should have been called once for all URLs
        assert url_extractor_with_cache.dedup_cache.exists_batch.call_count == 1
        # Cache should have been called to store URLs
        assert url_extractor_with_cache.dedup_cache.set.call_count == 4

    async def test_extract_urls_skip_cached(
        self, url_extractor_with_cache: URLExtractorService, sample_list_html: str
    ) -> None:
        """Test skipping URLs that exist in cache."""
        from crawler.utils.url import hash_url

        # Calculate the hash for the first URL to simulate it being cached
        first_url_hash = hash_url("https://example.com/article/1", normalize=True)

        # Mock batch exists to return the first URL as already cached
        async def mock_exists_batch(url_hashes: list[str]) -> set[str]:
            # Simulate first URL being cached
            return {first_url_hash}

        url_extractor_with_cache.dedup_cache.exists_batch = AsyncMock(side_effect=mock_exists_batch)

        results = await url_extractor_with_cache.extract_urls(
            html_content=sample_list_html,
            base_url="https://example.com",
            url_selector="a.article-link",
            deduplicate=True,
            job_id="job-123",
        )

        # Should skip the cached URL (first article)
        assert len(results) == 3  # 4 total - 1 cached = 3

        # Verify batch check was called
        assert url_extractor_with_cache.dedup_cache.exists_batch.call_count == 1

        # Verify the URLs don't include the cached one
        urls = [url.normalized_url for url in results]
        assert "https://example.com/article/1" not in urls
        assert "https://example.com/article/2" in urls
        assert "https://example.com/article/3" in urls
        assert "https://example.com/article/4" in urls

    async def test_extract_urls_no_deduplication(self, url_extractor: URLExtractorService) -> None:
        """Test extraction without deduplication."""
        html = """
        <html><body>
            <a href="/article/1" class="link">Link 1</a>
            <a href="/article/1" class="link">Link 1 Duplicate</a>
            <a href="/article/2" class="link">Link 2</a>
        </body></html>
        """

        results = await url_extractor.extract_urls(
            html_content=html,
            base_url="https://example.com",
            url_selector="a.link",
            deduplicate=False,
        )

        # Should have all 3 links including duplicates
        assert len(results) == 3

    async def test_extract_urls_empty_results(self, url_extractor: URLExtractorService) -> None:
        """Test extraction with no matching URLs."""
        html = "<html><body><p>No links here</p></body></html>"

        results = await url_extractor.extract_urls(
            html_content=html,
            base_url="https://example.com",
            url_selector="a.article-link",
            deduplicate=False,
        )

        assert results == []

    async def test_extract_urls_invalid_urls_skipped(
        self, url_extractor: URLExtractorService
    ) -> None:
        """Test that invalid URLs are skipped."""
        html = """
        <html><body>
            <a href="javascript:void(0)" class="link">Invalid</a>
            <a href="/article/1" class="link">Valid</a>
        </body></html>
        """

        results = await url_extractor.extract_urls(
            html_content=html,
            base_url="https://example.com",
            url_selector="a.link",
            deduplicate=False,
        )

        # javascript: URLs should be skipped during normalization
        # Only the valid URL should be extracted
        assert len(results) == 1
        assert results[0].normalized_url == "https://example.com/article/1"

    async def test_extract_urls_from_data_attributes(
        self, url_extractor: URLExtractorService, data_attribute_html: str
    ) -> None:
        """Test extracting URLs from data attributes."""
        results = await url_extractor.extract_urls_from_data_attributes(
            html_content=data_attribute_html,
            base_url="https://example.com",
            element_selector=".article",
            data_attribute="data-url",
            deduplicate=False,
        )

        assert len(results) == 2  # Only 2 have data-url attribute
        urls = [url.normalized_url for url in results]
        assert "https://example.com/article/1" in urls
        assert "https://example.com/article/2" in urls

    async def test_extract_urls_from_different_data_attribute(
        self, url_extractor: URLExtractorService, data_attribute_html: str
    ) -> None:
        """Test extracting URLs from different data attribute name."""
        results = await url_extractor.extract_urls_from_data_attributes(
            html_content=data_attribute_html,
            base_url="https://example.com",
            element_selector=".article",
            data_attribute="data-href",
            deduplicate=False,
        )

        assert len(results) == 1
        assert results[0].normalized_url == "https://example.com/article/3"

    async def test_parse_selector_config_string(self, url_extractor: URLExtractorService) -> None:
        """Test parsing string selector config."""
        selector, attribute, result_type, selector_type = url_extractor._parse_selector_config(
            "a.link"
        )

        assert selector == "a.link"
        assert attribute == "href"
        assert result_type == "array"
        assert selector_type == "css"

    async def test_parse_selector_config_object(self, url_extractor: URLExtractorService) -> None:
        """Test parsing SelectorConfig object."""
        config = SelectorConfig(selector=".article", attribute="data-url", type="single")

        selector, attribute, result_type, selector_type = url_extractor._parse_selector_config(
            config
        )

        assert selector == ".article"
        assert attribute == "data-url"
        assert result_type == "single"
        assert selector_type == "css"

    async def test_parse_selector_config_xpath(self, url_extractor: URLExtractorService) -> None:
        """Test parsing XPath selector."""
        config = SelectorConfig(selector="//a[@class='link']", attribute="href", type="array")

        selector, attribute, result_type, selector_type = url_extractor._parse_selector_config(
            config
        )

        assert selector == "//a[@class='link']"
        assert attribute == "href"
        assert result_type == "array"
        assert selector_type == "xpath"

    async def test_extracted_url_structure(
        self, url_extractor: URLExtractorService, sample_list_html: str
    ) -> None:
        """Test ExtractedURL dataclass structure."""
        results = await url_extractor.extract_urls(
            html_content=sample_list_html,
            base_url="https://example.com",
            url_selector="a.article-link",
            deduplicate=False,
        )

        first = results[0]
        assert hasattr(first, "url")
        assert hasattr(first, "normalized_url")
        assert hasattr(first, "url_hash")
        assert hasattr(first, "title")
        assert hasattr(first, "preview")
        assert hasattr(first, "metadata")

        # Check that URL hash is valid SHA-256 (64 hex chars)
        assert len(first.url_hash) == 64
        assert all(c in "0123456789abcdef" for c in first.url_hash)

    async def test_extract_urls_tracking_params_removed(
        self, url_extractor: URLExtractorService
    ) -> None:
        """Test that tracking parameters are removed during normalization."""
        html = """
        <html><body>
            <a href="/article?utm_source=facebook&utm_campaign=test" class="link">Article</a>
        </body></html>
        """

        results = await url_extractor.extract_urls(
            html_content=html,
            base_url="https://example.com",
            url_selector="a.link",
            deduplicate=False,
        )

        assert len(results) == 1
        # Normalized URL should have tracking params removed
        assert "utm_source" not in results[0].normalized_url
        assert "utm_campaign" not in results[0].normalized_url
        assert results[0].normalized_url == "https://example.com/article"

    async def test_extract_urls_preserves_semantic_params(
        self, url_extractor: URLExtractorService
    ) -> None:
        """Test that semantic parameters are preserved."""
        html = """
        <html><body>
            <a href="/article?page=2&category=tech&utm_source=fb" class="link">Article</a>
        </body></html>
        """

        results = await url_extractor.extract_urls(
            html_content=html,
            base_url="https://example.com",
            url_selector="a.link",
            deduplicate=False,
        )

        assert len(results) == 1
        normalized = results[0].normalized_url
        # Semantic params should be kept
        assert "page=2" in normalized
        assert "category=tech" in normalized
        # Tracking params should be removed
        assert "utm_source" not in normalized

    async def test_extract_urls_with_containers(self, url_extractor: URLExtractorService) -> None:
        """Test extracting URLs with containers for correct metadata association."""
        html = """
        <div class="article-list">
            <article class="post">
                <h2 class="title">First Article</h2>
                <p class="preview">First article preview</p>
                <a href="/article/1" class="link">Read more</a>
            </article>
            <article class="post">
                <h2 class="title">Second Article</h2>
                <p class="preview">Second article preview</p>
                <a href="/article/2" class="link">Read more</a>
            </article>
        </div>
        """

        results = await url_extractor.extract_urls(
            html_content=html,
            base_url="https://example.com",
            url_selector="a.link",
            metadata_selectors={"title": ".title", "preview": ".preview"},
            container_selector="article",
        )

        # Verify each URL got its own metadata
        assert len(results) == 2

        # First article
        assert results[0].url == "https://example.com/article/1"
        assert results[0].title == "First Article"
        assert results[0].preview == "First article preview"

        # Second article
        assert results[1].url == "https://example.com/article/2"
        assert results[1].title == "Second Article"
        assert results[1].preview == "Second article preview"
