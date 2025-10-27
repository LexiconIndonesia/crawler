"""Unit tests for API schemas (Pydantic models)."""

import pytest
from pydantic import ValidationError

from crawler.api.v1.schemas import (
    ActionConfig,
    BrowserTypeEnum,
    CrawlStep,
    CreateWebsiteRequest,
    GlobalConfig,
    HttpMethod,
    MethodEnum,
    PaginationConfig,
    RateLimitConfig,
    RetryConfig,
    ScheduleConfig,
    ScheduleTypeEnum,
    StepConfig,
    StepTypeEnum,
    TimeoutConfig,
)


class TestScheduleConfig:
    """Tests for ScheduleConfig model."""

    def test_schedule_config_defaults(self) -> None:
        """Test ScheduleConfig with default values."""
        schedule = ScheduleConfig()

        assert schedule.type == ScheduleTypeEnum.recurring
        assert schedule.cron == "0 0 1,15 * *"  # Bi-weekly default
        assert schedule.timezone == "UTC"
        assert schedule.enabled is True

    def test_schedule_config_custom_values(self) -> None:
        """Test ScheduleConfig with custom values."""
        schedule = ScheduleConfig(
            type=ScheduleTypeEnum.once,
            cron="0 2 * * 1",
            timezone="Asia/Jakarta",
            enabled=False,
        )

        assert schedule.type == ScheduleTypeEnum.once
        assert schedule.cron == "0 2 * * 1"
        assert schedule.timezone == "Asia/Jakarta"
        assert schedule.enabled is False


class TestStepConfig:
    """Tests for StepConfig model."""

    def test_step_config_defaults(self) -> None:
        """Test StepConfig with default values."""
        config = StepConfig()

        assert config.url is None
        assert config.http_method == HttpMethod.GET  # Extended model uses enum default
        assert config.headers is None  # Generated model defaults to None
        assert config.query_params is None  # Generated model defaults to None
        assert config.timeout == 30

    def test_step_config_with_pagination(self) -> None:
        """Test StepConfig with pagination configuration."""
        pagination = PaginationConfig(enabled=True, type="page_based", max_pages=50)
        config = StepConfig(url="https://example.com", pagination=pagination)

        assert config.url == "https://example.com"
        assert config.pagination is not None
        assert config.pagination.enabled is True
        assert config.pagination.max_pages == 50

    def test_step_config_allows_extra_fields(self) -> None:
        """Test that StepConfig allows extra fields."""
        config = StepConfig(
            url="https://example.com", custom_field="custom_value", another_field=123
        )

        assert config.url == "https://example.com"
        # Extra fields should be allowed
        assert hasattr(config, "custom_field")


class TestCrawlStep:
    """Tests for CrawlStep model."""

    def test_crawl_step_minimal(self) -> None:
        """Test CrawlStep with minimal required fields."""
        step = CrawlStep(name="test_step", type=StepTypeEnum.crawl, method=MethodEnum.api)

        assert step.name == "test_step"
        assert step.type == StepTypeEnum.crawl
        assert step.method == MethodEnum.api
        assert step.browser_type is None
        assert step.description is None

    def test_crawl_step_browser_requires_browser_type(self) -> None:
        """Test that browser method requires browser_type."""
        with pytest.raises(ValidationError, match="browser_type is required"):
            CrawlStep(
                name="test_step",
                type=StepTypeEnum.scrape,
                method=MethodEnum.browser,
                browser_type=None,  # Should fail validation
            )

    def test_crawl_step_browser_with_browser_type(self) -> None:
        """Test CrawlStep with browser method and browser_type."""
        step = CrawlStep(
            name="test_step",
            type=StepTypeEnum.scrape,
            method=MethodEnum.browser,
            browser_type=BrowserTypeEnum.playwright,
        )

        assert step.method == MethodEnum.browser
        assert step.browser_type == BrowserTypeEnum.playwright

    def test_crawl_step_with_selectors(self) -> None:
        """Test CrawlStep with selectors."""
        selectors = {
            "title": "h1.title",
            "content": "div.content",
            "author": {"selector": "span.author", "attribute": "text"},
        }

        step = CrawlStep(
            name="scrape_page",
            type=StepTypeEnum.scrape,
            method=MethodEnum.http,
            selectors=selectors,
        )

        assert step.selectors["title"] == "h1.title"
        # Generated model converts dict to SelectorConfig object
        assert step.selectors["author"].selector == "span.author"


class TestGlobalConfig:
    """Tests for GlobalConfig model."""

    def test_global_config_defaults(self) -> None:
        """Test GlobalConfig with default values."""
        config = GlobalConfig()

        # Generated model defaults to None for all fields
        assert config.rate_limit is None
        assert config.timeout is None
        assert config.retry is None
        assert config.headers is None
        assert config.cookies is None

    def test_global_config_custom_rate_limit(self) -> None:
        """Test GlobalConfig with custom rate limit."""
        rate_limit = RateLimitConfig(requests_per_second=5.0, concurrent_pages=10)
        config = GlobalConfig(rate_limit=rate_limit)

        assert config.rate_limit.requests_per_second == 5.0
        assert config.rate_limit.concurrent_pages == 10

    def test_global_config_custom_timeout(self) -> None:
        """Test GlobalConfig with custom timeout."""
        timeout = TimeoutConfig(page_load=60, selector_wait=20, http_request=45)
        config = GlobalConfig(timeout=timeout)

        assert config.timeout.page_load == 60
        assert config.timeout.selector_wait == 20
        assert config.timeout.http_request == 45


class TestRateLimitConfig:
    """Tests for RateLimitConfig validation."""

    def test_rate_limit_within_bounds(self) -> None:
        """Test RateLimitConfig with valid values."""
        config = RateLimitConfig(requests_per_second=2.5, concurrent_pages=10, burst=20)

        assert config.requests_per_second == 2.5
        assert config.concurrent_pages == 10
        assert config.burst == 20

    def test_rate_limit_requests_per_second_too_low(self) -> None:
        """Test RateLimitConfig with requests_per_second too low."""
        with pytest.raises(ValidationError):
            RateLimitConfig(requests_per_second=0.05)  # Below minimum 0.1

    def test_rate_limit_requests_per_second_too_high(self) -> None:
        """Test RateLimitConfig with requests_per_second too high."""
        with pytest.raises(ValidationError):
            RateLimitConfig(requests_per_second=150)  # Above maximum 100


class TestCreateWebsiteRequest:
    """Tests for CreateWebsiteRequest model."""

    def test_create_website_request_minimal(self) -> None:
        """Test CreateWebsiteRequest with minimal required fields."""
        request = CreateWebsiteRequest(
            name="Test Website",
            base_url="https://example.com",
            steps=[CrawlStep(name="fetch_data", type=StepTypeEnum.crawl, method=MethodEnum.api)],
        )

        assert request.name == "Test Website"
        assert str(request.base_url) == "https://example.com/"
        assert len(request.steps) == 1
        assert request.description is None
        assert isinstance(request.schedule, ScheduleConfig)
        assert isinstance(request.global_config, GlobalConfig)

    def test_create_website_request_full(self) -> None:
        """Test CreateWebsiteRequest with all fields."""
        schedule = ScheduleConfig(cron="0 0 * * *", timezone="Asia/Jakarta")
        steps = [
            CrawlStep(
                name="crawl_list",
                type=StepTypeEnum.crawl,
                method=MethodEnum.api,
                description="Get list of items",
            ),
            CrawlStep(
                name="scrape_detail",
                type=StepTypeEnum.scrape,
                method=MethodEnum.browser,
                browser_type=BrowserTypeEnum.playwright,
                description="Extract content",
            ),
        ]

        request = CreateWebsiteRequest(
            name="Test Website",
            base_url="https://example.com",
            description="Test website description",
            schedule=schedule,
            steps=steps,
            variables={"api_key": "secret", "page_size": 100},
        )

        assert request.name == "Test Website"
        assert request.description == "Test website description"
        assert request.schedule.timezone == "Asia/Jakarta"
        assert len(request.steps) == 2
        assert request.variables["api_key"] == "secret"

    def test_create_website_request_invalid_url(self) -> None:
        """Test CreateWebsiteRequest with invalid base_url."""
        # Pydantic AnyUrl validation catches invalid URLs before our custom validator
        with pytest.raises(ValidationError, match="Input should be a valid URL"):
            CreateWebsiteRequest(
                name="Test",
                base_url="invalid-url",
                steps=[CrawlStep(name="test", type=StepTypeEnum.crawl, method=MethodEnum.api)],
            )

    def test_create_website_request_empty_name(self) -> None:
        """Test CreateWebsiteRequest with empty name."""
        with pytest.raises(ValidationError):
            CreateWebsiteRequest(
                name="",
                base_url="https://example.com",
                steps=[CrawlStep(name="test", type=StepTypeEnum.crawl, method=MethodEnum.api)],
            )

    def test_create_website_request_no_steps(self) -> None:
        """Test CreateWebsiteRequest with no steps."""
        with pytest.raises(ValidationError, match="at least 1 item"):
            CreateWebsiteRequest(name="Test", base_url="https://example.com", steps=[])

    def test_create_website_request_duplicate_step_names(self) -> None:
        """Test CreateWebsiteRequest with duplicate step names."""
        with pytest.raises(ValidationError, match="Step names must be unique"):
            CreateWebsiteRequest(
                name="Test",
                base_url="https://example.com",
                steps=[
                    CrawlStep(name="duplicate", type=StepTypeEnum.crawl, method=MethodEnum.api),
                    CrawlStep(name="duplicate", type=StepTypeEnum.scrape, method=MethodEnum.http),
                ],
            )

    def test_create_website_request_name_too_long(self) -> None:
        """Test CreateWebsiteRequest with name exceeding max length."""
        with pytest.raises(ValidationError):
            CreateWebsiteRequest(
                name="x" * 256,  # Exceeds 255 max length
                base_url="https://example.com",
                steps=[CrawlStep(name="test", type=StepTypeEnum.crawl, method=MethodEnum.api)],
            )


class TestPaginationConfig:
    """Tests for PaginationConfig model."""

    def test_pagination_config_defaults(self) -> None:
        """Test PaginationConfig with defaults."""
        config = PaginationConfig()

        assert config.enabled is False
        assert config.type == "page_based"
        assert config.start_page == 1
        assert config.max_pages == 100

    def test_pagination_config_max_pages_validation(self) -> None:
        """Test PaginationConfig max_pages validation."""
        # Valid max_pages
        config = PaginationConfig(max_pages=500)
        assert config.max_pages == 500

        # Max_pages too high
        with pytest.raises(ValidationError):
            PaginationConfig(max_pages=2000)  # Exceeds maximum 1000

        # Max_pages too low
        with pytest.raises(ValidationError):
            PaginationConfig(max_pages=0)  # Below minimum 1

    def test_pagination_config_start_page_validation(self) -> None:
        """Test PaginationConfig start_page validation."""
        # Valid start_page
        config = PaginationConfig(start_page=5)
        assert config.start_page == 5

        # Start_page too low
        with pytest.raises(ValidationError):
            PaginationConfig(start_page=0)  # Below minimum 1


class TestActionConfig:
    """Tests for ActionConfig model."""

    def test_action_config_wait(self) -> None:
        """Test ActionConfig for wait action."""
        action = ActionConfig(type="wait", selector="div.content", timeout=10000)

        assert action.type.value == "wait"
        assert action.selector == "div.content"
        assert action.timeout == 10000
        assert action.optional is False

    def test_action_config_click_optional(self) -> None:
        """Test ActionConfig for optional click action."""
        action = ActionConfig(type="click", selector="button.load-more", optional=True)

        assert action.type.value == "click"
        assert action.optional is True

    def test_action_config_fill(self) -> None:
        """Test ActionConfig for fill action."""
        action = ActionConfig(type="fill", selector="input[name='search']", value="test query")

        assert action.type.value == "fill"
        assert action.value == "test query"

    def test_action_config_timeout_validation(self) -> None:
        """Test ActionConfig timeout validation."""
        # Valid timeout
        action = ActionConfig(type="wait", timeout=30000)
        assert action.timeout == 30000

        # Timeout too high
        with pytest.raises(ValidationError):
            ActionConfig(type="wait", timeout=120000)  # Exceeds 60000 max

        # Negative timeout
        with pytest.raises(ValidationError):
            ActionConfig(type="wait", timeout=-1)


class TestRetryConfig:
    """Tests for RetryConfig validation."""

    def test_retry_config_defaults(self) -> None:
        """Test RetryConfig with default values."""
        config = RetryConfig()

        assert config.max_attempts == 3
        assert config.backoff_strategy == "exponential"
        assert config.backoff_base == 2.0
        assert config.initial_delay == 1
        assert config.max_delay == 300

    def test_retry_config_custom_values(self) -> None:
        """Test RetryConfig with custom values."""
        config = RetryConfig(
            max_attempts=5,
            backoff_strategy="linear",
            initial_delay=2,
            max_delay=600,
        )

        assert config.max_attempts == 5
        assert config.backoff_strategy.value == "linear"
        assert config.initial_delay == 2
        assert config.max_delay == 600

    def test_retry_config_max_attempts_validation(self) -> None:
        """Test RetryConfig max_attempts validation."""
        # Valid max_attempts
        config = RetryConfig(max_attempts=5)
        assert config.max_attempts == 5

        # Max_attempts too high
        with pytest.raises(ValidationError):
            RetryConfig(max_attempts=15)  # Exceeds maximum 10

        # Max_attempts too low
        with pytest.raises(ValidationError):
            RetryConfig(max_attempts=0)  # Below minimum 1
