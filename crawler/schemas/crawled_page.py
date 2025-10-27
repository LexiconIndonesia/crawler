"""Pydantic schemas for CrawledPage table."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class CrawledPageBase(BaseModel):
    """Base crawled page schema with common fields."""

    website_id: str = Field(..., description="Website UUID")
    job_id: str = Field(..., description="Crawl job UUID")
    url: HttpUrl = Field(..., description="Page URL")
    url_hash: str = Field(..., min_length=64, max_length=64, description="SHA256 hash of URL")
    content_hash: str = Field(
        ..., min_length=64, max_length=64, description="SHA256 hash of content"
    )
    title: str | None = Field(None, max_length=500, description="Page title")
    extracted_content: str | None = Field(None, description="Extracted text content")
    metadata: dict[str, Any] | None = Field(
        None, description="Page metadata (headers, status, etc.)"
    )
    gcs_html_path: str | None = Field(None, max_length=1024, description="Path to HTML in GCS")
    gcs_documents: dict[str, Any] | None = Field(
        None, description="Paths to extracted documents in GCS"
    )
    is_duplicate: bool = Field(default=False, description="Whether page is a duplicate")
    duplicate_of: str | None = Field(None, description="UUID of original page if duplicate")
    similarity_score: int | None = Field(None, ge=0, le=100, description="Content similarity score")
    crawled_at: datetime = Field(..., description="When page was crawled")


class CrawledPageCreate(CrawledPageBase):
    """Schema for creating a new crawled page record.

    Example:
        {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "job_id": "987fcdeb-51a2-43f1-b4e5-123456789abc",
            "url": "https://example.com/page1",
            "url_hash": "a1b2c3...",
            "content_hash": "d4e5f6...",
            "title": "Example Page",
            "extracted_content": "This is the page content...",
            "metadata": {
                "status_code": 200,
                "content_type": "text/html"
            },
            "gcs_html_path": "gs://bucket/html/page1.html",
            "crawled_at": "2025-10-27T10:00:00Z"
        }
    """

    pass


class CrawledPageUpdate(BaseModel):
    """Schema for updating an existing crawled page.

    All fields are optional. Only provided fields will be updated.
    """

    title: str | None = Field(None, max_length=500)
    extracted_content: str | None = None
    metadata: dict[str, Any] | None = None
    gcs_html_path: str | None = Field(None, max_length=1024)
    gcs_documents: dict[str, Any] | None = None
    is_duplicate: bool | None = None
    duplicate_of: str | None = None
    similarity_score: int | None = Field(None, ge=0, le=100)


class CrawledPageResponse(CrawledPageBase):
    """Schema for crawled page API responses.

    Includes all fields including auto-generated ones.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Page UUID")
    created_at: datetime = Field(..., description="Record creation timestamp")


class CrawledPageListResponse(BaseModel):
    """Schema for paginated crawled page list responses."""

    pages: list[CrawledPageResponse]
    total: int
    page: int
    page_size: int


class CrawledPageStats(BaseModel):
    """Schema for crawled page statistics."""

    total_pages: int
    unique_pages: int
    duplicate_pages: int
    avg_similarity_score: float | None
    pages_by_status: dict[str, int]
