"""Pydantic schemas for Website table."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class WebsiteBase(BaseModel):
    """Base website schema with common fields."""

    name: str = Field(..., min_length=1, max_length=255, description="Unique website name")
    base_url: HttpUrl = Field(..., description="Base URL of the website")
    config: dict[str, Any] = Field(
        default_factory=dict, description="Website crawl configuration"
    )
    status: str = Field(default="active", description="Website status")
    created_by: str | None = Field(None, max_length=255, description="User who created")


class WebsiteCreate(WebsiteBase):
    """Schema for creating a new website.

    Example:
        {
            "name": "example-site",
            "base_url": "https://example.com",
            "config": {
                "max_depth": 3,
                "allowed_domains": ["example.com"],
                "user_agent": "CustomBot/1.0"
            },
            "created_by": "admin@example.com"
        }
    """

    pass


class WebsiteUpdate(BaseModel):
    """Schema for updating an existing website.

    All fields are optional. Only provided fields will be updated.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    base_url: HttpUrl | None = None
    config: dict[str, Any] | None = None
    status: str | None = None


class WebsiteResponse(WebsiteBase):
    """Schema for website API responses.

    Includes all fields including auto-generated ones.
    """

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Website UUID")
    created_at: datetime = Field(..., description="Creation timestamp")
    updated_at: datetime = Field(..., description="Last update timestamp")


class WebsiteListResponse(BaseModel):
    """Schema for paginated website list responses."""

    websites: list[WebsiteResponse]
    total: int
    page: int
    page_size: int
