"""Pydantic schemas for ScheduledJob table."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ScheduledJobBase(BaseModel):
    """Base scheduled job schema with common fields."""

    cron_schedule: str = Field(
        ...,
        min_length=9,
        max_length=255,
        description="Cron expression (e.g., '0 0 * * *' for daily at midnight)",
    )
    next_run_time: datetime = Field(..., description="Next scheduled execution time")
    is_active: bool = Field(default=True, description="Whether the schedule is active")
    job_config: dict[str, Any] = Field(
        default_factory=dict, description="Job-specific configuration overrides"
    )

    @field_validator("cron_schedule")
    @classmethod
    def validate_cron_schedule(cls, v: str) -> str:
        """Validate cron schedule format (basic validation)."""
        parts = v.strip().split()
        if len(parts) < 5 or len(parts) > 6:
            raise ValueError(
                "Cron schedule must have 5 or 6 parts (minute hour day month weekday [year])"
            )
        return v


class ScheduledJobCreate(ScheduledJobBase):
    """Schema for creating a new scheduled job.

    Example:
        {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "cron_schedule": "0 0 * * *",
            "next_run_time": "2025-10-28T00:00:00Z",
            "is_active": true,
            "job_config": {
                "max_depth": 5,
                "timeout": 30
            }
        }
    """

    website_id: str = Field(..., description="Website UUID")


class ScheduledJobUpdate(BaseModel):
    """Schema for updating an existing scheduled job.

    All fields are optional. Only provided fields will be updated.
    """

    cron_schedule: str | None = Field(None, min_length=9, max_length=255)
    next_run_time: datetime | None = None
    last_run_time: datetime | None = None
    is_active: bool | None = None
    job_config: dict[str, Any] | None = None

    @field_validator("cron_schedule")
    @classmethod
    def validate_cron_schedule(cls, v: str | None) -> str | None:
        """Validate cron schedule format (basic validation)."""
        if v is None:
            return v
        parts = v.strip().split()
        if len(parts) < 5 or len(parts) > 6:
            raise ValueError(
                "Cron schedule must have 5 or 6 parts (minute hour day month weekday [year])"
            )
        return v


class ScheduledJobResponse(ScheduledJobBase):
    """Schema for scheduled job API responses.

    Includes all fields including auto-generated ones.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Scheduled job UUID")
    website_id: str = Field(..., description="Website UUID")
    last_run_time: datetime | None = Field(None, description="Most recent execution time")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class ScheduledJobListResponse(BaseModel):
    """Schema for paginated scheduled job list responses."""

    jobs: list[ScheduledJobResponse]
    total: int
    page: int
    page_size: int


class ScheduledJobToggleStatus(BaseModel):
    """Schema for toggling scheduled job status."""

    is_active: bool = Field(..., description="New active status")
