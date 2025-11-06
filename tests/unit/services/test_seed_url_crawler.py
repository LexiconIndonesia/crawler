"""Unit tests for SeedURLCrawler selector extraction methods.

Tests the explicit key requirement for detail_urls and container selectors.
"""

from unittest.mock import AsyncMock

import pytest

from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum
from crawler.services import CrawlOutcome, SeedURLCrawler, SeedURLCrawlerConfig
from crawler.services.url_extractor import ExtractedURL
from crawler.utils.url import hash_url, normalize_url


@pytest.fixture
def crawler() -> SeedURLCrawler:
    """Create a SeedURLCrawler instance for testing."""
    return SeedURLCrawler()


class TestGetDetailUrlSelector:
    """Tests for _get_detail_url_selector method."""

    def test_returns_selector_with_detail_urls_key(self, crawler: SeedURLCrawler) -> None:
        """Test that detail_urls key is correctly extracted."""
        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a.product-link"},
            output=None,
        )

        result = crawler._get_detail_url_selector(step)
        assert result == "a.product-link"

    def test_returns_none_when_detail_urls_missing(self, crawler: SeedURLCrawler) -> None:
        """Test that None is returned when detail_urls key is missing."""
        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"urls": "a.link"},  # Wrong key - should not work
            output=None,
        )

        result = crawler._get_detail_url_selector(step)
        assert result is None

    def test_ignores_other_common_keys(self, crawler: SeedURLCrawler) -> None:
        """Test that other common keys like 'urls', 'links' are ignored."""
        for wrong_key in ["urls", "links", "articles", "items"]:
            step = CrawlStep(
                name="test",
                type=StepTypeEnum.crawl,
                description="Test step",
                method=MethodEnum.http,
                config=StepConfig(url="https://example.com"),
                selectors={wrong_key: "a.link"},
                output=None,
            )

            result = crawler._get_detail_url_selector(step)
            assert result is None, f"Should not accept '{wrong_key}' key"

    def test_returns_none_when_selectors_empty(self, crawler: SeedURLCrawler) -> None:
        """Test that None is returned when selectors dict is empty."""
        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={},
            output=None,
        )

        result = crawler._get_detail_url_selector(step)
        assert result is None


class TestGetContainerSelector:
    """Tests for _get_container_selector method."""

    def test_returns_selector_with_container_key(self, crawler: SeedURLCrawler) -> None:
        """Test that container key is correctly extracted."""
        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a.link", "container": "div.product-item"},
            output=None,
        )

        result = crawler._get_container_selector(step)
        assert result == "div.product-item"

    def test_returns_none_when_container_missing(self, crawler: SeedURLCrawler) -> None:
        """Test that None is returned when container key is missing."""
        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a.link"},  # No container
            output=None,
        )

        result = crawler._get_container_selector(step)
        assert result is None

    def test_ignores_other_common_keys(self, crawler: SeedURLCrawler) -> None:
        """Test that other common keys like 'item', 'article' are ignored."""
        for wrong_key in ["item", "article", "card"]:
            step = CrawlStep(
                name="test",
                type=StepTypeEnum.crawl,
                description="Test step",
                method=MethodEnum.http,
                config=StepConfig(url="https://example.com"),
                selectors={"detail_urls": "a.link", wrong_key: "div.item"},
                output=None,
            )

            result = crawler._get_container_selector(step)
            assert result is None, f"Should not accept '{wrong_key}' key"

    def test_returns_none_when_selectors_empty(self, crawler: SeedURLCrawler) -> None:
        """Test that None is returned when selectors dict is empty."""
        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={},
            output=None,
        )

        result = crawler._get_container_selector(step)
        assert result is None


class TestConfigValidation:
    """Tests for configuration validation with explicit keys."""

    def test_validation_fails_without_detail_urls_key(self, crawler: SeedURLCrawler) -> None:
        """Test that validation fails when detail_urls key is missing."""
        from crawler.services import SeedURLCrawlerConfig

        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"urls": "a.link"},  # Wrong key
            output=None,
        )

        config = SeedURLCrawlerConfig(step=step)
        error = crawler._validate_config(config)

        assert error is not None
        assert "detail_urls" in error
        assert "required" in error.lower()

    def test_validation_passes_with_detail_urls_key(self, crawler: SeedURLCrawler) -> None:
        """Test that validation passes when detail_urls key is present."""
        from crawler.services import SeedURLCrawlerConfig

        step = CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a.product-link"},
            output=None,
        )

        config = SeedURLCrawlerConfig(step=step)
        error = crawler._validate_config(config)

        assert error is None


class TestCancellationDetection:
    """Tests for job cancellation detection during crawl."""

    @pytest.fixture
    def sample_step(self) -> CrawlStep:
        """Create a sample step for testing."""
        return CrawlStep(
            name="test",
            type=StepTypeEnum.crawl,
            description="Test step",
            method=MethodEnum.http,
            config=StepConfig(url="https://example.com"),
            selectors={"detail_urls": "a.product-link"},
            output=None,
        )

    @pytest.mark.asyncio
    async def test_check_cancellation_returns_none_when_not_cancelled(
        self, crawler: SeedURLCrawler, sample_step: CrawlStep
    ) -> None:
        """Test that _check_cancellation returns None when job is not cancelled."""
        # Mock cancellation flag
        mock_flag = AsyncMock()
        mock_flag.is_cancelled.return_value = False

        config = SeedURLCrawlerConfig(
            step=sample_step, job_id="test-job-123", cancellation_flag=mock_flag
        )

        result = await crawler._check_cancellation(
            config=config,
            seed_url="https://example.com",
            pages_crawled=2,
            extracted_urls=[],
            warnings=None,
        )

        assert result is None
        mock_flag.is_cancelled.assert_awaited_once_with("test-job-123")

    @pytest.mark.asyncio
    async def test_check_cancellation_returns_result_when_cancelled(
        self, crawler: SeedURLCrawler, sample_step: CrawlStep
    ) -> None:
        """Test that _check_cancellation returns CrawlResult when job is cancelled."""
        # Mock cancellation flag
        mock_flag = AsyncMock()
        mock_flag.is_cancelled.return_value = True

        url = "https://example.com/product1"
        extracted_urls = [
            ExtractedURL(
                url=url,
                normalized_url=normalize_url(url),
                url_hash=hash_url(url),
            )
        ]

        config = SeedURLCrawlerConfig(
            step=sample_step, job_id="test-job-123", cancellation_flag=mock_flag
        )

        result = await crawler._check_cancellation(
            config=config,
            seed_url="https://example.com",
            pages_crawled=3,
            extracted_urls=extracted_urls,
            warnings=["test warning"],
        )

        assert result is not None
        assert result.outcome == CrawlOutcome.CANCELLED
        assert result.seed_url == "https://example.com"
        assert result.total_pages_crawled == 3
        assert result.total_urls_extracted == 1
        assert result.extracted_urls == extracted_urls
        assert result.error_message == "Job was cancelled during execution"
        assert result.warnings == ["test warning"]
        mock_flag.is_cancelled.assert_awaited_once_with("test-job-123")

    @pytest.mark.asyncio
    async def test_check_cancellation_without_flag(
        self, crawler: SeedURLCrawler, sample_step: CrawlStep
    ) -> None:
        """Test that _check_cancellation returns None when no cancellation flag is provided."""
        config = SeedURLCrawlerConfig(step=sample_step, job_id="test-job-123")

        result = await crawler._check_cancellation(
            config=config,
            seed_url="https://example.com",
            pages_crawled=1,
            extracted_urls=[],
        )

        assert result is None

    @pytest.mark.asyncio
    async def test_check_cancellation_without_job_id(
        self, crawler: SeedURLCrawler, sample_step: CrawlStep
    ) -> None:
        """Test that _check_cancellation returns None when no job_id is provided."""
        mock_flag = AsyncMock()
        mock_flag.is_cancelled.return_value = True

        config = SeedURLCrawlerConfig(step=sample_step, cancellation_flag=mock_flag)

        result = await crawler._check_cancellation(
            config=config,
            seed_url="https://example.com",
            pages_crawled=1,
            extracted_urls=[],
        )

        # Should return None because job_id is required for cancellation checks
        assert result is None
        mock_flag.is_cancelled.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_check_cancellation_preserves_extracted_urls(
        self, crawler: SeedURLCrawler, sample_step: CrawlStep
    ) -> None:
        """Test that cancellation preserves URLs extracted so far."""
        mock_flag = AsyncMock()
        mock_flag.is_cancelled.return_value = True

        url1 = "https://example.com/product1"
        url2 = "https://example.com/product2"
        url3 = "https://example.com/product3"
        extracted_urls = [
            ExtractedURL(
                url=url1,
                normalized_url=normalize_url(url1),
                url_hash=hash_url(url1),
            ),
            ExtractedURL(
                url=url2,
                normalized_url=normalize_url(url2),
                url_hash=hash_url(url2),
            ),
            ExtractedURL(
                url=url3,
                normalized_url=normalize_url(url3),
                url_hash=hash_url(url3),
            ),
        ]

        config = SeedURLCrawlerConfig(
            step=sample_step, job_id="test-job-123", cancellation_flag=mock_flag
        )

        result = await crawler._check_cancellation(
            config=config,
            seed_url="https://example.com",
            pages_crawled=2,
            extracted_urls=extracted_urls,
        )

        assert result is not None
        assert result.outcome == CrawlOutcome.CANCELLED
        assert result.total_urls_extracted == 3
        assert result.extracted_urls == extracted_urls
        assert len(result.extracted_urls) == 3
