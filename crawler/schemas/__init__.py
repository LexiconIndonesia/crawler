"""Pydantic schemas package.

This package contains all Pydantic schemas for API request/response validation
and data serialization for the crawler database tables.
"""

# Website schemas
from .content_hash import (
    ContentHashCreate,
    ContentHashResponse,
    ContentHashStats,
    ContentHashUpdate,
)

# CrawlJob schemas
from .crawl_job import (
    CrawlJobCancel,
    CrawlJobCreate,
    CrawlJobListResponse,
    CrawlJobResponse,
    CrawlJobUpdate,
)

# CrawlLog schemas
from .crawl_log import (
    CrawlLogCreate,
    CrawlLogFilter,
    CrawlLogListResponse,
    CrawlLogResponse,
)

# CrawledPage schemas
from .crawled_page import (
    CrawledPageCreate,
    CrawledPageListResponse,
    CrawledPageResponse,
    CrawledPageStats,
    CrawledPageUpdate,
)

# ScheduledJob schemas
from .scheduled_job import (
    ScheduledJobCreate,
    ScheduledJobListResponse,
    ScheduledJobResponse,
    ScheduledJobToggleStatus,
    ScheduledJobUpdate,
)
from .website import (
    WebsiteCreate,
    WebsiteListResponse,
    WebsiteResponse,
    WebsiteUpdate,
)

__all__ = [
    # Website
    "WebsiteCreate",
    "WebsiteUpdate",
    "WebsiteResponse",
    "WebsiteListResponse",
    # CrawlJob
    "CrawlJobCreate",
    "CrawlJobUpdate",
    "CrawlJobCancel",
    "CrawlJobResponse",
    "CrawlJobListResponse",
    # CrawledPage
    "CrawledPageCreate",
    "CrawledPageUpdate",
    "CrawledPageResponse",
    "CrawledPageListResponse",
    "CrawledPageStats",
    # ContentHash
    "ContentHashCreate",
    "ContentHashUpdate",
    "ContentHashResponse",
    "ContentHashStats",
    # CrawlLog
    "CrawlLogCreate",
    "CrawlLogResponse",
    "CrawlLogListResponse",
    "CrawlLogFilter",
    # ScheduledJob
    "ScheduledJobCreate",
    "ScheduledJobUpdate",
    "ScheduledJobResponse",
    "ScheduledJobListResponse",
    "ScheduledJobToggleStatus",
]
