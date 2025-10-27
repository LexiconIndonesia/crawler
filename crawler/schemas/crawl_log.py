"""Pydantic schemas for CrawlLog table."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CrawlLogBase(BaseModel):
    """Base crawl log schema with common fields."""

    job_id: str = Field(..., description="Crawl job UUID")
    website_id: str = Field(..., description="Website UUID")
    step_name: str | None = Field(None, max_length=255, description="Crawler step/phase name")
    log_level: str = Field(default="INFO", description="Log severity level")
    message: str = Field(..., description="Log message")
    context: dict[str, Any] | None = Field(None, description="Additional context data")
    trace_id: str | None = Field(None, description="Distributed tracing UUID")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper


class CrawlLogCreate(CrawlLogBase):
    """Schema for creating a new crawl log entry.

    Example:
        {
            "job_id": "123e4567-e89b-12d3-a456-426614174000",
            "website_id": "987fcdeb-51a2-43f1-b4e5-123456789abc",
            "step_name": "extract_content",
            "log_level": "INFO",
            "message": "Successfully extracted content from page",
            "context": {
                "url": "https://example.com/page1",
                "content_length": 1024,
                "duration_ms": 250
            },
            "trace_id": "abc123..."
        }
    """

    pass


class CrawlLogResponse(CrawlLogBase):
    """Schema for crawl log API responses.

    Includes all fields including auto-generated ones.
    """

    model_config = ConfigDict(from_attributes=True)

    id: int = Field(..., description="Auto-incrementing log ID")
    created_at: datetime = Field(..., description="Log timestamp")


class CrawlLogListResponse(BaseModel):
    """Schema for paginated crawl log list responses."""

    logs: list[CrawlLogResponse]
    total: int
    page: int
    page_size: int


class CrawlLogFilter(BaseModel):
    """Schema for filtering crawl logs."""

    job_id: str | None = None
    website_id: str | None = None
    log_level: str | None = None
    step_name: str | None = None
    trace_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str | None) -> str | None:
        """Validate log level is valid."""
        if v is None:
            return v
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"log_level must be one of {valid_levels}")
        return v_upper
