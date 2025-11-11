"""Step input/output validation for multi-step workflows.

This module provides validation for step inputs before execution and outputs after execution,
ensuring data integrity and catching issues early in the workflow pipeline.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from crawler.core.logging import get_logger

logger = get_logger(__name__)


class StepValidationError(ValueError):
    """Raised when step validation fails."""

    def __init__(self, step_name: str, errors: list[str], validation_type: str = "input"):
        """Initialize validation error.

        Args:
            step_name: Name of the step that failed validation
            errors: List of validation error messages
            validation_type: Type of validation (input/output)
        """
        self.step_name = step_name
        self.errors = errors
        self.validation_type = validation_type
        error_list = "; ".join(errors)
        super().__init__(f"Step '{step_name}' {validation_type} validation failed: {error_list}")


# ============================================================================
# Input Validation Schemas
# ============================================================================


class CrawlStepInput(BaseModel):
    """Input validation schema for crawl steps.

    Crawl steps expect either:
    - A single string URL (seed URL)
    - A list containing a single URL (first URL is used as seed)
    """

    url: str | list[str] = Field(..., description="Seed URL or list with seed URL")

    @field_validator("url")
    @classmethod
    def validate_url_not_empty(cls, v: str | list[str]) -> str | list[str]:
        """Validate URL is not empty."""
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("URL cannot be empty string")
        elif isinstance(v, list):
            if len(v) == 0:
                raise ValueError("URL list cannot be empty")
            if not isinstance(v[0], str):
                raise ValueError("First URL in list must be a string")
            if not v[0].strip():
                raise ValueError("First URL in list cannot be empty string")
        return v

    @property
    def seed_url(self) -> str:
        """Get the seed URL from input."""
        if isinstance(self.url, str):
            return self.url
        return self.url[0]


class ScrapeStepInput(BaseModel):
    """Input validation schema for scrape steps.

    Scrape steps expect:
    - A single string URL, or
    - A list of string URLs
    """

    urls: str | list[str] = Field(..., description="URL or list of URLs to scrape")

    @field_validator("urls")
    @classmethod
    def validate_urls_not_empty(cls, v: str | list[str]) -> str | list[str]:
        """Validate URLs are not empty."""
        if isinstance(v, str):
            if not v.strip():
                raise ValueError("URL cannot be empty string")
        elif isinstance(v, list):
            if len(v) == 0:
                raise ValueError("URL list cannot be empty")
            for i, url in enumerate(v):
                if not isinstance(url, str):
                    raise ValueError(f"URL at index {i} must be a string, got {type(url).__name__}")
                if not url.strip():
                    raise ValueError(f"URL at index {i} cannot be empty string")
        return v

    @property
    def url_list(self) -> list[str]:
        """Get URLs as a list."""
        if isinstance(self.urls, str):
            return [self.urls]
        return self.urls


# ============================================================================
# Output Validation Schemas
# ============================================================================


class CrawlStepOutput(BaseModel):
    """Output validation schema for crawl steps.

    Crawl steps should produce:
    - extracted_data: dict with at least one field (typically 'urls')
    - metadata: dict with crawl statistics
    """

    extracted_data: dict[str, Any] = Field(..., description="Extracted data from crawl")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Crawl metadata")

    @field_validator("extracted_data")
    @classmethod
    def validate_extracted_data_not_empty(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate extracted data is not empty."""
        if not v:
            raise ValueError("Crawl step must extract at least one field")
        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata_structure(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate metadata contains expected fields."""
        # Optional: Check for expected metadata fields
        # For now, just ensure it's a dict
        if not isinstance(v, dict):
            raise ValueError("Metadata must be a dictionary")
        return v


class ScrapeStepOutput(BaseModel):
    """Output validation schema for scrape steps.

    Scrape steps should produce:
    - extracted_data: dict or dict with 'items' key for multiple URLs
    - metadata: dict with scrape statistics (total_urls, successful_urls, failed_urls)
    """

    extracted_data: dict[str, Any] = Field(..., description="Extracted data from scrape")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Scrape metadata")

    @field_validator("extracted_data")
    @classmethod
    def validate_extracted_data(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate extracted data structure."""
        if not isinstance(v, dict):
            raise ValueError("Extracted data must be a dictionary")

        # For multi-URL scrapes, expect 'items' key with list
        if "items" in v:
            if not isinstance(v["items"], list):
                raise ValueError("'items' field must be a list")
            # Can be empty list if all URLs failed
        # For single URL, just check it's a dict (can be empty if extraction failed)

        return v

    @field_validator("metadata")
    @classmethod
    def validate_metadata_statistics(cls, v: dict[str, Any]) -> dict[str, Any]:
        """Validate metadata contains scrape statistics."""
        # Check for expected metadata fields
        expected_fields = {"total_urls", "successful_urls", "failed_urls"}
        if expected_fields.issubset(v.keys()):
            # Validate counts are non-negative integers
            for field in expected_fields:
                if not isinstance(v[field], int) or v[field] < 0:
                    raise ValueError(f"Metadata field '{field}' must be a non-negative integer")
        # Metadata fields are optional - not all executors set them
        return v


# ============================================================================
# Step Validator
# ============================================================================


class StepValidator:
    """Validates step inputs and outputs against expected schemas.

    This validator ensures:
    1. Input data matches expected format before execution
    2. Output data matches expected format after execution
    3. Required fields are present
    4. Data types are correct
    """

    def __init__(self) -> None:
        """Initialize step validator."""
        # Map step types to input schemas
        self.input_schemas: dict[str, type[BaseModel]] = {
            "crawl": CrawlStepInput,
            "scrape": ScrapeStepInput,
        }

        # Map step types to output schemas
        self.output_schemas: dict[str, type[BaseModel]] = {
            "crawl": CrawlStepOutput,
            "scrape": ScrapeStepOutput,
        }

    def validate_input(
        self,
        step_name: str,
        step_type: str,
        input_data: Any,
        strict: bool = True,
    ) -> dict[str, Any]:
        """Validate step input before execution.

        Args:
            step_name: Name of the step
            step_type: Type of step (crawl/scrape)
            input_data: Input data to validate (URL or URLs)
            strict: If True, raise exception on validation failure; if False, log warning

        Returns:
            Validated input data as dict

        Raises:
            StepValidationError: If validation fails and strict=True
        """
        # Guard: unsupported step type
        if step_type not in self.input_schemas:
            logger.warning(
                "input_validation_skipped",
                step_name=step_name,
                step_type=step_type,
                reason="unsupported_step_type",
            )
            return {"url": input_data} if step_type == "crawl" else {"urls": input_data}

        schema = self.input_schemas[step_type]

        try:
            # Validate input based on step type
            if step_type == "crawl":
                validated = schema(url=input_data)
            else:  # scrape
                validated = schema(urls=input_data)

            logger.debug(
                "input_validation_success",
                step_name=step_name,
                step_type=step_type,
            )

            return validated.model_dump()

        except ValidationError as e:
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            logger.error(
                "input_validation_failed",
                step_name=step_name,
                step_type=step_type,
                errors=errors,
            )

            if strict:
                raise StepValidationError(
                    step_name=step_name,
                    errors=errors,
                    validation_type="input",
                ) from e

            # Non-strict mode: return original data with warning
            logger.warning(
                "input_validation_non_strict",
                step_name=step_name,
                message="Proceeding with invalid input",
            )
            return {"url": input_data} if step_type == "crawl" else {"urls": input_data}

    def validate_output(
        self,
        step_name: str,
        step_type: str,
        extracted_data: dict[str, Any],
        metadata: dict[str, Any],
        strict: bool = False,
    ) -> dict[str, Any]:
        """Validate step output after execution.

        Args:
            step_name: Name of the step
            step_type: Type of step (crawl/scrape)
            extracted_data: Extracted data from step execution
            metadata: Metadata from step execution
            strict: If True, raise exception on validation failure; if False, log warning

        Returns:
            Validated output data as dict

        Raises:
            StepValidationError: If validation fails and strict=True
        """
        # Guard: unsupported step type
        if step_type not in self.output_schemas:
            logger.warning(
                "output_validation_skipped",
                step_name=step_name,
                step_type=step_type,
                reason="unsupported_step_type",
            )
            return {"extracted_data": extracted_data, "metadata": metadata}

        schema = self.output_schemas[step_type]

        try:
            validated = schema(
                extracted_data=extracted_data,
                metadata=metadata,
            )

            logger.debug(
                "output_validation_success",
                step_name=step_name,
                step_type=step_type,
                extracted_fields=len(extracted_data),
            )

            return validated.model_dump()

        except ValidationError as e:
            errors = [f"{err['loc'][0]}: {err['msg']}" for err in e.errors()]
            logger.error(
                "output_validation_failed",
                step_name=step_name,
                step_type=step_type,
                errors=errors,
            )

            if strict:
                raise StepValidationError(
                    step_name=step_name,
                    errors=errors,
                    validation_type="output",
                ) from e

            # Non-strict mode: return original data with warning
            logger.warning(
                "output_validation_non_strict",
                step_name=step_name,
                message="Proceeding with invalid output",
            )
            return {"extracted_data": extracted_data, "metadata": metadata}

    def validate_required_fields(
        self,
        step_name: str,
        step_type: str,
        extracted_data: dict[str, Any],
        required_fields: list[str] | None = None,
    ) -> list[str]:
        """Validate that required fields are present in extracted data.

        Args:
            step_name: Name of the step
            step_type: Type of step
            extracted_data: Extracted data to check
            required_fields: List of required field names (if None, uses step type defaults)

        Returns:
            List of missing required fields (empty if all present)
        """
        # Default required fields by step type
        if required_fields is None:
            if step_type == "crawl":
                # Crawl steps typically extract URLs
                required_fields = []  # Flexible - any extraction is valid
            elif step_type == "scrape":
                # Scrape steps extract content
                required_fields = []  # Flexible - any extraction is valid
            else:
                required_fields = []

        missing = [field for field in required_fields if field not in extracted_data]

        if missing:
            logger.warning(
                "required_fields_missing",
                step_name=step_name,
                step_type=step_type,
                missing_fields=missing,
            )

        return missing
