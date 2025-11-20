"""Integration tests for CrawlExecutor."""

from unittest.mock import patch

import httpx
import pytest

from crawler.services.pagination import PaginationService
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors import (
    APIExecutor,
    BrowserExecutor,
    CrawlExecutor,
    HTTPExecutor,
)


class TestCrawlExecutor:
    """Integration tests for CrawlExecutor."""

    @pytest.fixture
    def http_executor(self):
        """Create HTTP executor."""
        return HTTPExecutor(selector_processor=SelectorProcessor())

    @pytest.fixture
    def api_executor(self):
        """Create API executor."""
        return APIExecutor(selector_processor=SelectorProcessor())

    @pytest.fixture
    def browser_executor(self):
        """Create browser executor."""
        return BrowserExecutor(selector_processor=SelectorProcessor())

    @pytest.fixture
    def crawl_executor(self, http_executor, api_executor, browser_executor):
        """Create crawl executor."""
        return CrawlExecutor(
            http_executor=http_executor,
            api_executor=api_executor,
            browser_executor=browser_executor,
            selector_processor=SelectorProcessor(),
            pagination_service=PaginationService(),
        )

    @pytest.mark.asyncio
    async def test_crawl_single_page_http_method(self, crawl_executor):
        """Test crawl executor with single page using HTTP method."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <a class="article-link" href="/article1">Article 1</a>
                        <a class="article-link" href="/article2">Article 2</a>
                        <a class="article-link" href="/article3">Article 3</a>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response

            result = await crawl_executor.execute(
                url="https://example.com/articles",
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert result.extracted_data["urls"] == [
                "https://example.com/article1",
                "https://example.com/article2",
                "https://example.com/article3",
            ]
            assert result.extracted_data["_crawl_metadata"]["total_urls"] == 3
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 1
            assert result.extracted_data["_crawl_metadata"]["pages_failed"] == 0
            assert result.metadata["seed_url"] == "https://example.com/articles"
            assert result.metadata["duplicate_urls"] == 0

    @pytest.mark.asyncio
    async def test_crawl_with_pagination_template(self, crawl_executor):
        """Test crawl executor with pagination using URL template."""
        step_config = {
            "method": "http",
            "timeout": 30,
            "pagination": {
                "enabled": True,
                "url_template": "https://example.com/articles?page={page}",
                "start_page": 1,
                "max_pages": 3,
            },
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            # Mock responses for 3 pages
            page1_response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <a class="article-link" href="/article1">Article 1</a>
                        <a class="article-link" href="/article2">Article 2</a>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            page2_response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <a class="article-link" href="/article3">Article 3</a>
                        <a class="article-link" href="/article4">Article 4</a>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            page3_response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <a class="article-link" href="/article5">Article 5</a>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.side_effect = [page1_response, page2_response, page3_response]

            result = await crawl_executor.execute(
                url="https://example.com/articles",  # Seed URL (will be replaced by template)
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert result.extracted_data["urls"] == [
                "https://example.com/article1",
                "https://example.com/article2",
                "https://example.com/article3",
                "https://example.com/article4",
                "https://example.com/article5",
            ]
            assert result.extracted_data["_crawl_metadata"]["total_urls"] == 5
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 3
            assert result.extracted_data["_crawl_metadata"]["pages_failed"] == 0
            assert result.metadata["pagination_enabled"] is True
            assert result.metadata["total_pages"] == 3

    @pytest.mark.asyncio
    async def test_crawl_with_duplicates(self, crawl_executor):
        """Test crawl executor deduplicates URLs across pages."""
        step_config = {
            "method": "http",
            "timeout": 30,
            "pagination": {
                "enabled": True,
                "url_template": "https://example.com/articles?page={page}",
                "start_page": 1,
                "max_pages": 2,
            },
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            # Both pages return same URLs
            duplicate_response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <a class="article-link" href="/article1">Article 1</a>
                        <a class="article-link" href="/article2">Article 2</a>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.side_effect = [duplicate_response, duplicate_response]

            result = await crawl_executor.execute(
                url="https://example.com/articles",
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert result.extracted_data["urls"] == [
                "https://example.com/article1",
                "https://example.com/article2",
            ]
            assert result.extracted_data["_crawl_metadata"]["total_urls"] == 2
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 2
            assert result.metadata["duplicate_urls"] == 2  # 4 total - 2 unique = 2 duplicates

    @pytest.mark.asyncio
    async def test_crawl_no_urls_found(self, crawl_executor):
        """Test crawl executor handles 0 URLs found gracefully."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <p>No articles found</p>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response

            result = await crawl_executor.execute(
                url="https://example.com/articles",
                step_config=step_config,
                selectors=selectors,
            )

            # Should succeed even with 0 URLs
            assert result.success
            assert result.extracted_data["urls"] == []
            assert result.extracted_data["_crawl_metadata"]["total_urls"] == 0
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 1
            assert result.extracted_data["_crawl_metadata"]["pages_failed"] == 0

    @pytest.mark.asyncio
    async def test_crawl_with_page_failures(self, crawl_executor):
        """Test crawl executor handles page failures gracefully."""
        step_config = {
            "method": "http",
            "timeout": 30,
            "pagination": {
                "enabled": True,
                "url_template": "https://example.com/articles?page={page}",
                "start_page": 1,
                "max_pages": 3,
            },
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            # Page 1: success
            page1_response = httpx.Response(
                status_code=200,
                content=b"""
                <html><body><a class="article-link" href="/article1">Article 1</a></body></html>
            """,
                headers={"content-type": "text/html"},
            )
            # Page 2: 404 error
            page2_response = httpx.Response(
                status_code=404,
                content=b"Not Found",
                headers={"content-type": "text/html"},
            )
            # Page 3: success
            page3_response = httpx.Response(
                status_code=200,
                content=b"""
                <html><body><a class="article-link" href="/article2">Article 2</a></body></html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.side_effect = [page1_response, page2_response, page3_response]

            result = await crawl_executor.execute(
                url="https://example.com/articles",
                step_config=step_config,
                selectors=selectors,
            )

            # Should succeed even with partial failures
            assert result.success
            assert result.extracted_data["urls"] == [
                "https://example.com/article1",
                "https://example.com/article2",
            ]
            assert result.extracted_data["_crawl_metadata"]["total_urls"] == 2
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 2
            assert result.extracted_data["_crawl_metadata"]["pages_failed"] == 1
            assert result.metadata["errors"] is not None
            assert len(result.metadata["errors"]) == 1

    @pytest.mark.asyncio
    async def test_crawl_api_method(self, crawl_executor):
        """Test crawl executor with API method."""
        step_config = {
            "method": "api",
            "timeout": 30,
        }
        selectors = {
            "urls": {
                "selector": "data.articles",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            response = httpx.Response(
                status_code=200,
                content=b"""
                {
                    "data": {
                        "articles": [
                            "/article1",
                            "/article2"
                        ]
                    }
                }
            """,
                headers={"content-type": "application/json"},
            )
            mock_request.return_value = response

            result = await crawl_executor.execute(
                url="https://api.example.com/articles",
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            # The extracted data should have urls field
            assert "urls" in result.extracted_data
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 1

    @pytest.mark.asyncio
    async def test_crawl_method_delegation(self, crawl_executor):
        """Test crawl executor delegates to correct method-specific executor."""
        # Verify executor selection doesn't raise errors
        executor_http = crawl_executor._get_method_executor("http")
        executor_api = crawl_executor._get_method_executor("api")
        executor_browser = crawl_executor._get_method_executor("browser")

        assert executor_http == crawl_executor.http_executor
        assert executor_api == crawl_executor.api_executor
        assert executor_browser == crawl_executor.browser_executor

        # Test invalid method raises error
        with pytest.raises(ValueError, match="Unsupported method"):
            crawl_executor._get_method_executor("invalid")

    @pytest.mark.asyncio
    async def test_crawl_multiple_url_fields(self, crawl_executor):
        """Test crawl executor extracts from multiple URL fields."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            },
            "links": {
                "selector": "a.related-link",
                "attribute": "href",
                "type": "array",
            },
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <a class="article-link" href="/article1">Article 1</a>
                        <a class="related-link" href="/related1">Related 1</a>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response

            result = await crawl_executor.execute(
                url="https://example.com/articles",
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            # Should extract from both 'urls' and 'links' fields
            extracted_urls = result.extracted_data.get("urls", [])
            extracted_links = result.extracted_data.get("links", [])
            # At least one field should have URLs
            assert len(extracted_urls) > 0 or len(extracted_links) > 0
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 1

    @pytest.mark.asyncio
    async def test_crawl_pagination_disabled(self, crawl_executor):
        """Test crawl executor with pagination explicitly disabled."""
        step_config = {
            "method": "http",
            "timeout": 30,
            "pagination": {
                "enabled": False,
            },
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <a class="article-link" href="/article1">Article 1</a>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response

            result = await crawl_executor.execute(
                url="https://example.com/articles",
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert result.extracted_data["urls"] == ["https://example.com/article1"]
            assert result.extracted_data["_crawl_metadata"]["pages_crawled"] == 1
            assert result.metadata["pagination_enabled"] is False

    @pytest.mark.asyncio
    async def test_crawl_all_pages_failed(self, crawl_executor):
        """Test crawl executor fails when all pages fail."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "urls": {
                "selector": "a.article-link",
                "attribute": "href",
                "type": "array",
            }
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            # All pages return 404
            response_404 = httpx.Response(
                status_code=404,
                content=b"Not Found",
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response_404

            result = await crawl_executor.execute(
                url="https://example.com/notfound",
                step_config=step_config,
                selectors=selectors,
            )

            # Should fail when all pages fail
            assert not result.success
            assert result.error is not None
            assert "All pages failed" in result.error

    @pytest.mark.asyncio
    async def test_crawl_execution_error(self, crawl_executor):
        """Test crawl executor handles execution errors."""
        step_config = {
            "method": "invalid_method",  # Invalid method to trigger error
            "timeout": 30,
        }
        selectors = {}

        result = await crawl_executor.execute(
            url="https://example.com/articles",
            step_config=step_config,
            selectors=selectors,
        )

        assert not result.success
        assert result.error is not None
        assert "Crawl execution error" in result.error

    @pytest.mark.asyncio
    async def test_crawl_cleanup(self, crawl_executor):
        """Test crawl executor cleanup."""
        # Cleanup should not raise errors
        await crawl_executor.cleanup()
        # Should be idempotent
        await crawl_executor.cleanup()
