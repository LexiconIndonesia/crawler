"""Pydantic schemas for ContentHash table."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContentHashBase(BaseModel):
    """Base content hash schema with common fields."""

    content_hash: str = Field(
        ..., min_length=64, max_length=64, description="SHA256 content hash"
    )
    first_seen_page_id: str | None = Field(
        None, description="UUID of first page with this content"
    )
    occurrence_count: int = Field(default=1, ge=1, description="Number of occurrences")
    last_seen_at: datetime = Field(..., description="Last time content was seen")


class ContentHashCreate(ContentHashBase):
    """Schema for creating a new content hash record.

    Example:
        {
            "content_hash": "a1b2c3d4e5f6...",
            "first_seen_page_id": "123e4567-e89b-12d3-a456-426614174000",
            "occurrence_count": 1,
            "last_seen_at": "2025-10-27T10:00:00Z"
        }
    """

    pass


class ContentHashUpdate(BaseModel):
    """Schema for updating an existing content hash record.

    Typically used to increment occurrence count and update last_seen_at.
    """

    occurrence_count: int | None = Field(None, ge=1)
    last_seen_at: datetime | None = None


class ContentHashResponse(ContentHashBase):
    """Schema for content hash API responses.

    Includes all fields including auto-generated ones.
    """

    model_config = ConfigDict(from_attributes=True)

    created_at: datetime = Field(..., description="First occurrence timestamp")


class ContentHashStats(BaseModel):
    """Schema for content hash statistics."""

    total_hashes: int
    total_occurrences: int
    avg_occurrences: float
    most_common: list[tuple[str, int]]  # (content_hash, count) pairs
