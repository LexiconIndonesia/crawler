"""Pydantic schemas for CrawlJob table."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class CrawlJobBase(BaseModel):
    """Base crawl job schema with common fields."""

    website_id: str = Field(..., description="Website UUID")
    job_type: str = Field(default="one_time", description="Type of crawl job")
    seed_url: HttpUrl = Field(..., description="Starting URL for crawl")
    embedded_config: dict[str, Any] | None = Field(
        None, description="Job-specific configuration overrides"
    )
    status: str = Field(default="pending", description="Current job status")
    priority: int = Field(default=5, ge=1, le=10, description="Job priority (1-10)")
    scheduled_at: datetime | None = Field(None, description="When job is scheduled to run")
    max_retries: int = Field(default=3, ge=0, description="Maximum retry attempts")
    metadata: dict[str, Any] | None = Field(None, description="Additional job metadata")
    variables: dict[str, Any] | None = Field(None, description="Runtime variables")

    @field_validator("job_type")
    @classmethod
    def validate_job_type(cls, v: str) -> str:
        """Validate job type is valid."""
        valid_types = {"one_time", "scheduled", "recurring"}
        if v not in valid_types:
            raise ValueError(f"job_type must be one of {valid_types}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        """Validate status is valid."""
        valid_statuses = {"pending", "running", "completed", "failed", "cancelled"}
        if v not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}")
        return v


class CrawlJobCreate(CrawlJobBase):
    """Schema for creating a new crawl job.

    Example:
        {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "job_type": "one_time",
            "seed_url": "https://example.com",
            "priority": 7,
            "embedded_config": {
                "max_pages": 100,
                "timeout": 30
            },
            "metadata": {
                "triggered_by": "api",
                "notes": "Full site crawl"
            }
        }
    """

    pass


class CrawlJobUpdate(BaseModel):
    """Schema for updating an existing crawl job.

    All fields are optional. Only provided fields will be updated.
    """

    status: str | None = None
    priority: int | None = Field(None, ge=1, le=10)
    scheduled_at: datetime | None = None
    embedded_config: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    variables: dict[str, Any] | None = None
    error_message: str | None = None

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str | None) -> str | None:
        """Validate status is valid."""
        if v is None:
            return v
        valid_statuses = {"pending", "running", "completed", "failed", "cancelled"}
        if v not in valid_statuses:
            raise ValueError(f"status must be one of {valid_statuses}")
        return v


class CrawlJobCancel(BaseModel):
    """Schema for cancelling a crawl job."""

    cancelled_by: str = Field(..., max_length=255, description="User who cancelled")
    cancellation_reason: str | None = Field(None, description="Reason for cancellation")


class CrawlJobResponse(CrawlJobBase):
    """Schema for crawl job API responses.

    Includes all fields including auto-generated and execution state.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Job UUID")
    started_at: datetime | None = Field(None, description="Job start time")
    completed_at: datetime | None = Field(None, description="Job completion time")
    cancelled_at: datetime | None = Field(None, description="Job cancellation time")
    cancelled_by: str | None = Field(None, description="User who cancelled")
    cancellation_reason: str | None = Field(None, description="Cancellation reason")
    error_message: str | None = Field(None, description="Error details if failed")
    retry_count: int = Field(default=0, description="Current retry count")
    progress: dict[str, Any] | None = Field(None, description="Job progress data")
    created_at: datetime = Field(..., description="Job creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class CrawlJobListResponse(BaseModel):
    """Schema for paginated crawl job list responses."""

    jobs: list[CrawlJobResponse]
    total: int
    page: int
    page_size: int
