"""Website-specific schemas for API v1."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from crawler.api.schemas import StatusEnum

# ============================================================================
# Enums
# ============================================================================


class ScheduleTypeEnum(str, Enum):
    """Schedule type for website crawling."""

    ONCE = "once"
    RECURRING = "recurring"


class StepTypeEnum(str, Enum):
    """Type of crawl step."""

    CRAWL = "crawl"
    SCRAPE = "scrape"


class MethodEnum(str, Enum):
    """Method used for crawling/scraping."""

    API = "api"
    BROWSER = "browser"
    HTTP = "http"


class BrowserTypeEnum(str, Enum):
    """Browser type for automation."""

    PLAYWRIGHT = "playwright"
    UNDETECTED_CHROMEDRIVER = "undetected_chromedriver"

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ACTIVE = "active"
    INACTIVE = "inactive"


# ============================================================================
# Selector Models
# ============================================================================


class SelectorConfig(BaseModel):
    """Configuration for a single selector."""

    selector: str = Field(..., description="CSS selector or XPath expression")
    attribute: str | None = Field(
        default="text",
        description="Attribute to extract (text, html, href, src, etc.)",
        examples=["text", "href", "content", "src"],
    )
    type: str = Field(
        default="single", description="Type of selector result", examples=["single", "array"]
    )


class Selectors(BaseModel):
    """Selectors for extracting data from pages.

    Can be a simple string selector or a detailed SelectorConfig.
    """

    model_config = {"extra": "allow"}  # Allow additional dynamic fields


# ============================================================================
# Step Configuration Models
# ============================================================================


class PaginationConfig(BaseModel):
    """Pagination configuration."""

    enabled: bool = Field(default=False, description="Enable pagination")
    type: str = Field(
        default="page_based",
        description="Pagination type",
        examples=["page_based", "offset_based", "cursor_based", "next_button", "url_pattern"],
    )
    page_param: str | None = Field(default="page", description="Page parameter name")
    start_page: int = Field(default=1, ge=1, description="Starting page number")
    max_pages: int = Field(default=100, ge=1, le=1000, description="Maximum pages to crawl")
    selector: str | None = Field(default=None, description="Next button selector (for browser)")
    wait_after_click: int | None = Field(
        default=2000, ge=0, description="Wait time after clicking next (ms)"
    )
    url_template: str | None = Field(
        default=None, description="URL template with {page} placeholder"
    )


class ActionConfig(BaseModel):
    """Browser action configuration."""

    type: str = Field(
        ...,
        description="Action type",
        examples=["wait", "click", "fill", "scroll", "execute_script", "hover"],
    )
    selector: str | None = Field(default=None, description="Element selector")
    value: str | None = Field(default=None, description="Value for fill actions")
    timeout: int = Field(default=5000, ge=0, le=60000, description="Action timeout (ms)")
    optional: bool = Field(default=False, description="Continue if action fails")


class StepConfig(BaseModel):
    """Step-specific configuration (API/Browser/HTTP methods)."""

    url: str | None = Field(default=None, description="URL to fetch (supports variables)")
    http_method: str = Field(default="GET", description="HTTP method", examples=["GET", "POST"])
    headers: dict[str, str] = Field(default_factory=dict, description="HTTP headers")
    query_params: dict[str, Any] = Field(default_factory=dict, description="Query parameters")
    pagination: PaginationConfig | None = Field(default=None, description="Pagination config")
    wait_until: str | None = Field(
        default="networkidle",
        description="Browser wait condition",
        examples=["load", "domcontentloaded", "networkidle"],
    )
    actions: list[ActionConfig] = Field(default_factory=list, description="Browser actions")
    timeout: int = Field(default=30, ge=1, le=300, description="Request timeout (seconds)")

    model_config = {"extra": "allow"}  # Allow additional fields


class OutputConfig(BaseModel):
    """Output configuration for step results."""

    urls_field: str | None = Field(
        default="detail_urls", description="Field name for extracted URLs"
    )
    main_content_field: str | None = Field(default="content", description="Main content field name")
    metadata_fields: list[str] = Field(
        default_factory=list, description="Metadata fields to extract"
    )


class CrawlStep(BaseModel):
    """A single crawl/scrape step in the workflow."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique step name")
    type: StepTypeEnum = Field(..., description="Step type (crawl or scrape)")
    description: str | None = Field(default=None, description="Human-readable description")
    method: MethodEnum = Field(..., description="Method to use (api, browser, http)")
    browser_type: BrowserTypeEnum | None = Field(
        default=None, description="Browser type (if method=browser)"
    )
    input_from: str | None = Field(
        default=None,
        description="Input data source from previous step (e.g., 'crawl_list.detail_urls')",
    )
    config: StepConfig = Field(
        default_factory=StepConfig, description="Step-specific configuration"
    )
    selectors: dict[str, str | dict[str, Any]] = Field(
        default_factory=dict, description="CSS/XPath selectors for data extraction"
    )
    output: OutputConfig = Field(default_factory=OutputConfig, description="Output configuration")

    @model_validator(mode="after")
    def validate_browser_type(self) -> "CrawlStep":
        """Validate browser_type is set when method is browser."""
        if self.method == MethodEnum.BROWSER and self.browser_type is None:
            raise ValueError("browser_type is required when method is 'browser'")
        return self


# ============================================================================
# Website Configuration Models
# ============================================================================


class ScheduleConfig(BaseModel):
    """Schedule configuration for recurring crawls."""

    type: ScheduleTypeEnum = Field(default=ScheduleTypeEnum.RECURRING, description="Schedule type")
    cron: str = Field(
        default="0 0 1,15 * *",
        description="Cron expression (minute hour day month weekday)",
        examples=["0 0 1,15 * *", "0 2 * * 1", "*/30 * * * *"],
    )
    timezone: str = Field(
        default="UTC", description="Timezone for schedule", examples=["UTC", "Asia/Jakarta"]
    )
    enabled: bool = Field(default=True, description="Enable/disable schedule")


class RateLimitConfig(BaseModel):
    """Rate limiting configuration."""

    requests_per_second: float = Field(
        default=2.0, ge=0.1, le=100, description="Max requests per second"
    )
    concurrent_pages: int = Field(default=5, ge=1, le=50, description="Max concurrent pages")
    burst: int = Field(default=10, ge=1, le=100, description="Max burst requests")


class TimeoutConfig(BaseModel):
    """Timeout configuration."""

    page_load: int = Field(default=30, ge=5, le=300, description="Page load timeout (seconds)")
    selector_wait: int = Field(
        default=10, ge=1, le=60, description="Selector wait timeout (seconds)"
    )
    http_request: int = Field(
        default=30, ge=5, le=300, description="HTTP request timeout (seconds)"
    )


class RetryConfig(BaseModel):
    """Retry configuration."""

    max_attempts: int = Field(default=3, ge=1, le=10, description="Maximum retry attempts")
    backoff_strategy: str = Field(
        default="exponential",
        description="Backoff strategy",
        examples=["exponential", "linear", "fixed"],
    )
    backoff_base: float = Field(default=2.0, ge=1.0, le=10.0, description="Backoff base multiplier")
    initial_delay: int = Field(default=1, ge=1, le=60, description="Initial delay (seconds)")
    max_delay: int = Field(default=300, ge=1, le=3600, description="Maximum delay (seconds)")


class GlobalConfig(BaseModel):
    """Global configuration applied to all steps."""

    rate_limit: RateLimitConfig = Field(
        default_factory=RateLimitConfig, description="Rate limiting"
    )
    timeout: TimeoutConfig = Field(default_factory=TimeoutConfig, description="Timeouts")
    retry: RetryConfig = Field(default_factory=RetryConfig, description="Retry logic")
    headers: dict[str, str] = Field(default_factory=dict, description="Global HTTP headers")
    cookies: dict[str, str] = Field(default_factory=dict, description="Global cookies")

    model_config = {"extra": "allow"}  # Allow proxy, authentication, etc.


# ============================================================================
# Request/Response Models
# ============================================================================


class CreateWebsiteRequest(BaseModel):
    """Request model for creating a website configuration."""

    name: str = Field(
        ...,
        min_length=1,
        max_length=255,
        description="Unique website name",
        examples=["Example News Site"],
    )
    base_url: str = Field(
        ...,
        min_length=1,
        max_length=2048,
        description="Base URL of the website",
        examples=["https://example.com"],
    )
    description: str | None = Field(default=None, description="Optional description")
    schedule: ScheduleConfig = Field(
        default_factory=ScheduleConfig, description="Schedule configuration for recurring crawls"
    )
    steps: list[CrawlStep] = Field(
        ..., min_length=1, description="List of crawl/scrape steps to execute"
    )
    global_config: GlobalConfig = Field(
        default_factory=GlobalConfig, description="Global configuration"
    )
    variables: dict[str, Any] = Field(
        default_factory=dict, description="Variables for substitution"
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base_url is a valid URL."""
        if not v.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def validate_step_names_unique(self) -> "CreateWebsiteRequest":
        """Validate step names are unique."""
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step names must be unique")
        return self


class WebsiteResponse(BaseModel):
    """Response model for website with scheduling info."""

    id: UUID = Field(..., description="Website ID")
    name: str = Field(..., description="Website name")
    base_url: str = Field(..., description="Base URL")
    config: dict[str, Any] = Field(..., description="Full configuration")
    status: StatusEnum = Field(..., description="Website status")
    cron_schedule: str | None = Field(None, description="Cron schedule expression")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")
    created_by: str | None = Field(None, description="Creator identifier")
    next_run_time: datetime | None = Field(
        None, description="Next scheduled crawl time (if scheduled job exists)"
    )
    scheduled_job_id: UUID | None = Field(None, description="Associated scheduled job ID")

    model_config = {"from_attributes": True}
