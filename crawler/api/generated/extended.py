"""Extended models with custom validators.

This module extends the auto-generated models with custom business logic validators.
"""

from typing import TypeVar

from pydantic import BaseModel, Field, field_validator, model_validator

from .models import (
    BackoffStrategy,
    HttpMethod,
    MethodEnum,
    ScheduleTypeEnum,
    WaitUntil,
)
from .models import (
    CrawlStep as _CrawlStep,
)
from .models import (
    CreateSeedJobInlineRequest as _CreateSeedJobInlineRequest,
)
from .models import (
    CreateSeedJobRequest as _CreateSeedJobRequest,
)
from .models import (
    CreateWebsiteRequest as _CreateWebsiteRequest,
)
from .models import (
    GlobalConfig as _GlobalConfig,
)
from .models import (
    UpdateWebsiteRequest as _UpdateWebsiteRequest,
)
from .models import (
    RetryConfig as _RetryConfig,
)
from .models import (
    ScheduleConfig as _ScheduleConfig,
)
from .models import (
    StepConfig as _StepConfig,
)

# Type variable for mixin self-reference
T = TypeVar("T", bound=BaseModel)


class EnumSerializationMixin(BaseModel):
    """Base mixin for models that need to serialize enums as their values.

    This mixin configures Pydantic to serialize enum fields as their string values
    instead of enum objects, preventing serialization warnings and ensuring consistent
    JSON representation.

    Usage:
        class MyConfig(EnumSerializationMixin, _MyConfig):
            my_enum_field: MyEnum = MyEnum.default_value
    """

    model_config = {
        "use_enum_values": True,  # Serialize enums as their values
    }


class StepNamesValidationMixin(BaseModel):
    """Mixin for validating step names are unique.

    This mixin provides a shared validator for models that have a `steps` field
    containing a list of CrawlStep objects. It ensures all step names are unique.

    Usage:
        class MyRequest(StepNamesValidationMixin, _MyRequest):
            steps: list[CrawlStep]
    """

    @model_validator(mode="after")
    def validate_step_names_unique(self: T) -> T:
        """Validate step names are unique across all steps.

        Raises:
            ValueError: If duplicate step names are found
        """
        if hasattr(self, "steps") and self.steps is not None:
            step_names = [step.name for step in self.steps]
            if len(step_names) != len(set(step_names)):
                raise ValueError("Step names must be unique")
        return self


class BrowserTypeValidationMixin(BaseModel):
    """Mixin for validating browser_type is set when method is browser.

    This mixin provides a shared validator for models that have a `steps` field
    containing a list of CrawlStep objects. It ensures that when a step's method
    is 'browser', the browser_type field is also set.

    Usage:
        class MyRequest(BrowserTypeValidationMixin, _MyRequest):
            steps: list[CrawlStep]
    """

    @model_validator(mode="after")
    def validate_browser_type(self: T) -> T:
        """Validate browser_type is set when method is browser.

        Raises:
            ValueError: If a step has method='browser' but browser_type is None
        """
        if hasattr(self, "steps") and self.steps is not None:
            for step in self.steps:
                if step.method == MethodEnum.browser and step.browser_type is None:
                    raise ValueError("browser_type is required when method is 'browser'")
        return self


class CreateSeedJobRequest(_CreateSeedJobRequest):
    """Extended CreateSeedJobRequest with non-nullable priority field."""

    # Override to make priority non-nullable (defaults to 5 per OpenAPI spec)
    priority: int = 5


class ScheduleConfig(_ScheduleConfig):
    """Extended ScheduleConfig with proper enum defaults and validation."""

    # Override to use enum instead of string
    type: ScheduleTypeEnum = ScheduleTypeEnum.recurring

    @model_validator(mode="after")
    def ensure_type_is_enum(self) -> "ScheduleConfig":
        """Ensure type is always an enum, converting string defaults if needed."""
        if isinstance(self.type, str):
            self.type = ScheduleTypeEnum(self.type)
        return self


class RetryConfig(EnumSerializationMixin, _RetryConfig):
    """Extended RetryConfig with proper enum defaults to fix serialization warnings."""

    # Override to use enum defaults instead of string literals
    backoff_strategy: BackoffStrategy | None = BackoffStrategy.exponential


class StepConfig(EnumSerializationMixin, _StepConfig):
    """Extended StepConfig with proper enum defaults to fix serialization warnings."""

    # Override to use enum defaults instead of string literals
    http_method: HttpMethod | None = HttpMethod.GET
    wait_until: WaitUntil | None = WaitUntil.networkidle


class GlobalConfig(_GlobalConfig):
    """Extended GlobalConfig with proper enum defaults to fix serialization warnings."""

    # Override retry field to use extended RetryConfig with proper enum defaults
    retry: RetryConfig | None = None


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


class CreateWebsiteRequest(
    StepNamesValidationMixin, BrowserTypeValidationMixin, _CreateWebsiteRequest
):
    """Extended CreateWebsiteRequest with custom validators.

    Inherits step name validation from StepNamesValidationMixin and browser type
    validation from BrowserTypeValidationMixin.
    """

    # Override with default values to match original behavior
    schedule: ScheduleConfig = Field(default_factory=ScheduleConfig)
    global_config: GlobalConfig = Field(default_factory=GlobalConfig)
    # Use extended CrawlStep with validators and proper enum serialization
    steps: list[CrawlStep] = Field(
        description="List of crawl/scrape steps to execute", min_length=1
    )

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, v: str) -> str:
        """Validate base_url is a valid URL."""
        # Convert AnyUrl to string if needed
        url_str = str(v) if not isinstance(v, str) else v
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("base_url must start with http:// or https://")
        return v


class CreateSeedJobInlineRequest(
    StepNamesValidationMixin, BrowserTypeValidationMixin, _CreateSeedJobInlineRequest
):
    """Extended CreateSeedJobInlineRequest with custom validators.

    Inherits step name validation from StepNamesValidationMixin and browser type
    validation from BrowserTypeValidationMixin.
    """

    # Override to make priority non-nullable (defaults to 5 per OpenAPI spec)
    priority: int = 5
    # Override with default value for global_config
    global_config: GlobalConfig = Field(default_factory=GlobalConfig)
    # Use extended CrawlStep with validators and proper enum serialization
    steps: list[CrawlStep] = Field(
        description="List of crawl/scrape steps to execute", min_length=1
    )

    @field_validator("seed_url")
    @classmethod
    def validate_seed_url(cls, v: str) -> str:
        """Validate seed_url is a valid URL."""
        # Convert AnyUrl to string if needed
        url_str = str(v) if not isinstance(v, str) else v
        if not url_str.startswith(("http://", "https://")):
            raise ValueError("seed_url must start with http:// or https://")
        return v


class UpdateWebsiteRequest(
    StepNamesValidationMixin, BrowserTypeValidationMixin, _UpdateWebsiteRequest
):
    """Extended UpdateWebsiteRequest that uses extended ScheduleConfig.

    This ensures proper enum handling for the schedule.type field.
    """

    # Override schedule field to use our extended ScheduleConfig
    schedule: ScheduleConfig | None = None
    # Override steps field to use our extended CrawlStep
    steps: list[CrawlStep] | None = None
    # Override global_config field to use our extended GlobalConfig
    global_config: GlobalConfig | None = None
