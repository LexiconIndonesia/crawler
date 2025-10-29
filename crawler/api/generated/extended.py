"""Extended models with custom validators.

This module extends the auto-generated models with custom business logic validators.
"""

from typing import Annotated

from pydantic import Field, field_validator, model_validator

from .models import (
    CreateSeedJobInlineRequest as _CreateSeedJobInlineRequest,
    CreateSeedJobRequest as _CreateSeedJobRequest,
    CreateWebsiteRequest as _CreateWebsiteRequest,
    CrawlStep as _CrawlStep,
    GlobalConfig,
    HttpMethod,
    MethodEnum,
    ScheduleConfig as _ScheduleConfig,
    ScheduleTypeEnum,
    StepConfig as _StepConfig,
    WaitUntil,
)


class CreateSeedJobRequest(_CreateSeedJobRequest):
    """Extended CreateSeedJobRequest with non-nullable priority field."""

    # Override to make priority non-nullable (defaults to 5 per OpenAPI spec)
    priority: int = 5


class ScheduleConfig(_ScheduleConfig):
    """Extended ScheduleConfig with proper enum defaults."""

    # Override to use enum instead of string
    type: ScheduleTypeEnum = ScheduleTypeEnum.recurring


class StepConfig(_StepConfig):
    """Extended StepConfig with proper enum defaults to fix serialization warnings."""

    # Override to use enum defaults instead of string literals
    http_method: HttpMethod | None = HttpMethod.GET
    wait_until: WaitUntil | None = WaitUntil.networkidle


class CrawlStep(_CrawlStep):
    """Extended CrawlStep with custom validators."""

    # Override to use extended StepConfig with proper enum defaults
    config: StepConfig | None = None

    @model_validator(mode="after")
    def validate_browser_type(self) -> "CrawlStep":
        """Validate browser_type is set when method is browser."""
        if self.method == MethodEnum.browser and self.browser_type is None:
            raise ValueError("browser_type is required when method is 'browser'")
        return self


class CreateWebsiteRequest(_CreateWebsiteRequest):
    """Extended CreateWebsiteRequest with custom validators."""

    # Override with default values to match original behavior
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    global_config: GlobalConfig = Field(default_factory=GlobalConfig)
    # Use extended CrawlStep with validators
    steps: Annotated[
        list[CrawlStep],
        Field(description="List of crawl/scrape steps to execute", min_length=1),
    ]

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base_url is a valid URL."""
        # Convert AnyUrl to string if needed
        url_str = str(v) if not isinstance(v, str) else v
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def validate_step_names_unique(self) -> "CreateWebsiteRequest":
        """Validate step names are unique."""
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step names must be unique")
        return self


class CreateSeedJobInlineRequest(_CreateSeedJobInlineRequest):
    """Extended CreateSeedJobInlineRequest with custom validators."""

    # Override to make priority non-nullable (defaults to 5 per OpenAPI spec)
    priority: int = 5
    # Override with default value for global_config
    global_config: GlobalConfig = Field(default_factory=GlobalConfig)
    # Use extended CrawlStep with validators
    steps: Annotated[
        list[CrawlStep],
        Field(description="List of crawl/scrape steps to execute", min_length=1),
    ]

    @field_validator("seed_url")
    @classmethod
    def validate_seed_url(cls, v: str) -> str:
        """Validate seed_url is a valid URL."""
        # Convert AnyUrl to string if needed
        url_str = str(v) if not isinstance(v, str) else v
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("seed_url must start with http:// or https://")
        return v

    @model_validator(mode="after")
    def validate_step_names_unique(self) -> "CreateSeedJobInlineRequest":
        """Validate step names are unique."""
        step_names = [step.name for step in self.steps]
        if len(step_names) != len(set(step_names)):
            raise ValueError("Step names must be unique")
        return self
