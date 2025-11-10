"""Integration tests for ScrapeExecutor."""

from unittest.mock import patch

import httpx
import pytest

from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors import (
    APIExecutor,
    BrowserExecutor,
    HTTPExecutor,
    ScrapeExecutor,
)


class TestScrapeExecutor:
    """Integration tests for ScrapeExecutor."""

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
    def scrape_executor(self, http_executor, api_executor, browser_executor):
        """Create scrape executor."""
        return ScrapeExecutor(
            http_executor=http_executor,
            api_executor=api_executor,
            browser_executor=browser_executor,
            selector_processor=SelectorProcessor(),
        )

    @pytest.mark.asyncio
    async def test_scrape_single_url(self, scrape_executor):
        """Test scraping a single URL."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "title": "h1.title",
            "content": ".article-body",
        }

        with patch("httpx.AsyncClient.request") as mock_request:
            response = httpx.Response(
                status_code=200,
                content=b"""
                <html>
                    <body>
                        <h1 class="title">Article Title</h1>
                        <div class="article-body">Article content here</div>
                    </body>
                </html>
            """,
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response

            result = await scrape_executor.execute(
                url="https://example.com/article/1",
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert result.extracted_data["title"] == "Article Title"
            assert result.extracted_data["content"] == "Article content here"
            assert result.metadata["total_urls"] == 1
            assert result.metadata["successful_urls"] == 1
            assert result.metadata["failed_urls"] == 0

    @pytest.mark.asyncio
    async def test_scrape_multiple_urls(self, scrape_executor):
        """Test scraping multiple URLs."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "title": "h1.title",
            "content": ".article-body",
        }

        urls = [
            "https://example.com/article/1",
            "https://example.com/article/2",
            "https://example.com/article/3",
        ]

        with patch("httpx.AsyncClient.request") as mock_request:
            # Mock responses for each URL
            responses = [
                httpx.Response(
                    status_code=200,
                    content=f"""
                    <html>
                        <body>
                            <h1 class="title">Article {i}</h1>
                            <div class="article-body">Content {i}</div>
                        </body>
                    </html>
                """.encode(),
                    headers={"content-type": "text/html"},
                )
                for i in range(1, 4)
            ]
            mock_request.side_effect = responses

            result = await scrape_executor.execute(
                url=urls,
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert "items" in result.extracted_data
            assert len(result.extracted_data["items"]) == 3
            assert result.extracted_data["items"][0]["title"] == "Article 1"
            assert result.extracted_data["items"][1]["title"] == "Article 2"
            assert result.extracted_data["items"][2]["title"] == "Article 3"
            assert result.metadata["total_urls"] == 3
            assert result.metadata["successful_urls"] == 3
            assert result.metadata["failed_urls"] == 0

    @pytest.mark.asyncio
    async def test_scrape_with_partial_failures(self, scrape_executor):
        """Test scraping handles partial failures gracefully."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "title": "h1.title",
        }

        urls = [
            "https://example.com/article/1",
            "https://example.com/article/2",
            "https://example.com/article/3",
        ]

        with patch("httpx.AsyncClient.request") as mock_request:
            # First URL succeeds, second fails, third succeeds
            responses = [
                httpx.Response(
                    status_code=200,
                    content=b'<html><body><h1 class="title">Article 1</h1></body></html>',
                    headers={"content-type": "text/html"},
                ),
                httpx.Response(
                    status_code=404,
                    content=b"Not Found",
                    headers={"content-type": "text/html"},
                ),
                httpx.Response(
                    status_code=200,
                    content=b'<html><body><h1 class="title">Article 3</h1></body></html>',
                    headers={"content-type": "text/html"},
                ),
            ]
            mock_request.side_effect = responses

            result = await scrape_executor.execute(
                url=urls,
                step_config=step_config,
                selectors=selectors,
            )

            # Should succeed with partial results
            assert result.success
            assert "items" in result.extracted_data
            assert len(result.extracted_data["items"]) == 2
            assert result.extracted_data["items"][0]["title"] == "Article 1"
            assert result.extracted_data["items"][1]["title"] == "Article 3"
            assert result.metadata["total_urls"] == 3
            assert result.metadata["successful_urls"] == 2
            assert result.metadata["failed_urls"] == 1
            assert result.metadata["errors"] is not None
            assert len(result.metadata["errors"]) == 1

    @pytest.mark.asyncio
    async def test_scrape_all_urls_failed(self, scrape_executor):
        """Test scraping fails when all URLs fail."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "title": "h1.title",
        }

        urls = [
            "https://example.com/article/1",
            "https://example.com/article/2",
        ]

        with patch("httpx.AsyncClient.request") as mock_request:
            # All URLs return 404
            response_404 = httpx.Response(
                status_code=404,
                content=b"Not Found",
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response_404

            result = await scrape_executor.execute(
                url=urls,
                step_config=step_config,
                selectors=selectors,
            )

            # Should fail when all URLs fail
            assert not result.success
            assert result.error is not None
            assert "All URLs failed" in result.error
            assert result.metadata["total_urls"] == 2
            assert result.metadata["failed_urls"] == 2

    @pytest.mark.asyncio
    async def test_scrape_batch_processing(self, scrape_executor):
        """Test scraping processes URLs in batches."""
        # Create executor with small batch size for testing
        scrape_executor.batch_size = 2

        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "title": "h1",
        }

        # Create 5 URLs (should be processed in 3 batches: 2, 2, 1)
        urls = [f"https://example.com/article/{i}" for i in range(1, 6)]

        with patch("httpx.AsyncClient.request") as mock_request:
            # Mock responses for all URLs
            responses = [
                httpx.Response(
                    status_code=200,
                    content=f"<html><body><h1>Article {i}</h1></body></html>".encode(),
                    headers={"content-type": "text/html"},
                )
                for i in range(1, 6)
            ]
            mock_request.side_effect = responses

            result = await scrape_executor.execute(
                url=urls,
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert len(result.extracted_data["items"]) == 5
            assert result.metadata["total_urls"] == 5
            assert result.metadata["successful_urls"] == 5
            # Verify all requests were made (batching doesn't skip URLs)
            assert mock_request.call_count == 5

    @pytest.mark.asyncio
    async def test_scrape_empty_url_list(self, scrape_executor):
        """Test scraping handles empty URL list gracefully."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {}

        result = await scrape_executor.execute(
            url=[],
            step_config=step_config,
            selectors=selectors,
        )

        assert result.success
        assert result.extracted_data == {}
        assert result.metadata["total_urls"] == 0
        assert result.metadata["successful_urls"] == 0
        assert result.metadata["failed_urls"] == 0

    @pytest.mark.asyncio
    async def test_scrape_api_method(self, scrape_executor):
        """Test scraping with API method."""
        step_config = {
            "method": "api",
            "timeout": 30,
        }
        selectors = {
            "title": "data.title",
            "author": "data.author",
        }

        urls = [
            "https://api.example.com/articles/1",
            "https://api.example.com/articles/2",
        ]

        with patch("httpx.AsyncClient.request") as mock_request:
            responses = [
                httpx.Response(
                    status_code=200,
                    content=b'{"data": {"title": "Article 1", "author": "Author 1"}}',
                    headers={"content-type": "application/json"},
                ),
                httpx.Response(
                    status_code=200,
                    content=b'{"data": {"title": "Article 2", "author": "Author 2"}}',
                    headers={"content-type": "application/json"},
                ),
            ]
            mock_request.side_effect = responses

            result = await scrape_executor.execute(
                url=urls,
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert len(result.extracted_data["items"]) == 2
            assert result.extracted_data["items"][0]["title"] == "Article 1"
            assert result.extracted_data["items"][1]["author"] == "Author 2"

    @pytest.mark.asyncio
    async def test_scrape_method_delegation(self, scrape_executor):
        """Test scrape executor delegates to correct method-specific executor."""
        # Verify executor selection
        executor_http = scrape_executor._get_method_executor("http")
        executor_api = scrape_executor._get_method_executor("api")
        executor_browser = scrape_executor._get_method_executor("browser")

        assert executor_http == scrape_executor.http_executor
        assert executor_api == scrape_executor.api_executor
        assert executor_browser == scrape_executor.browser_executor

        # Test invalid method raises error
        with pytest.raises(ValueError, match="Unsupported method"):
            scrape_executor._get_method_executor("invalid")

    @pytest.mark.asyncio
    async def test_scrape_execution_error(self, scrape_executor):
        """Test scraping handles execution errors."""
        step_config = {
            "method": "invalid_method",  # Invalid method
            "timeout": 30,
        }
        selectors = {}

        result = await scrape_executor.execute(
            url="https://example.com/article/1",
            step_config=step_config,
            selectors=selectors,
        )

        assert not result.success
        assert result.error is not None
        assert "Scrape execution error" in result.error

    @pytest.mark.asyncio
    async def test_scrape_large_batch(self, scrape_executor):
        """Test scraping handles batches larger than default size."""
        step_config = {
            "method": "http",
            "timeout": 30,
        }
        selectors = {
            "title": "h1",
        }

        # Create 150 URLs (should trigger batching with default size 100)
        urls = [f"https://example.com/article/{i}" for i in range(150)]

        with patch("httpx.AsyncClient.request") as mock_request:
            # Mock all responses
            response = httpx.Response(
                status_code=200,
                content=b"<html><body><h1>Article</h1></body></html>",
                headers={"content-type": "text/html"},
            )
            mock_request.return_value = response

            result = await scrape_executor.execute(
                url=urls,
                step_config=step_config,
                selectors=selectors,
            )

            assert result.success
            assert len(result.extracted_data["items"]) == 150
            assert result.metadata["total_urls"] == 150
            assert result.metadata["successful_urls"] == 150
            # Verify all requests were made
            assert mock_request.call_count == 150

    @pytest.mark.asyncio
    async def test_scrape_cleanup(self, scrape_executor):
        """Test scrape executor cleanup."""
        # Cleanup should not raise errors
        await scrape_executor.cleanup()
        # Should be idempotent
        await scrape_executor.cleanup()
