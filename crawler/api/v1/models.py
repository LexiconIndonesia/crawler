"""API v1 response models."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DuplicatePageInfo(BaseModel):
    """Information about a duplicate page in a group."""

    id: int = Field(description="Relationship ID")
    duplicate_page_id: UUID = Field(description="UUID of the duplicate page")
    url: str = Field(description="Page URL")
    content_hash: str = Field(description="Content hash of the page")
    detection_method: str = Field(description="How the duplicate was detected")
    similarity_score: int | None = Field(description="Similarity percentage (0-100)")
    confidence_threshold: int | None = Field(description="Detection confidence threshold")
    detected_at: datetime = Field(description="When the duplicate was detected")
    detected_by: str | None = Field(description="System/user that detected the duplicate")
    crawled_at: datetime = Field(description="When the page was originally crawled")


class DuplicateGroupDetails(BaseModel):
    """Detailed information about a duplicate group."""

    id: UUID = Field(description="Group ID")
    canonical_page_id: UUID = Field(description="UUID of the canonical page")
    canonical_url: str = Field(description="URL of the canonical page")
    canonical_content_hash: str = Field(description="Content hash of the canonical page")
    canonical_crawled_at: datetime = Field(description="When canonical page was crawled")
    group_size: int = Field(description="Total number of pages in group (including canonical)")
    created_at: datetime = Field(description="When the group was created")
    updated_at: datetime = Field(description="When the group was last updated")
    duplicates: list[DuplicatePageInfo] = Field(description="List of duplicate pages")


class DuplicateGroupStats(BaseModel):
    """Statistics for a duplicate group."""

    id: UUID = Field(description="Group ID")
    canonical_page_id: UUID = Field(description="UUID of the canonical page")
    group_size: int = Field(description="Total number of pages in group")
    relationship_count: int = Field(description="Number of duplicate relationships")
    avg_similarity: float | None = Field(description="Average similarity score")
    first_detected: datetime | None = Field(description="When first duplicate was detected")
    last_detected: datetime | None = Field(description="When last duplicate was detected")


class DuplicateGroupsList(BaseModel):
    """Paginated list of duplicate groups."""

    groups: list[dict] = Field(description="List of duplicate groups")
    total: int = Field(description="Total number of groups")
    limit: int = Field(description="Number of groups per page")
    offset: int = Field(description="Offset for pagination")
