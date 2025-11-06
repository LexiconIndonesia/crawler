"""Unit tests for SeedURLCrawler selector extraction methods.

Tests the explicit key requirement for detail_urls and container selectors.
"""

import pytest

from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum
from crawler.services import SeedURLCrawler


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
