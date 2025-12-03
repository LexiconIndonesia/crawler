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
    # ContentHash
    "ContentHashCreate",
    "ContentHashResponse",
    "ContentHashStats",
    "ContentHashUpdate",
    "CrawlJobCancel",
    # CrawlJob
    "CrawlJobCreate",
    "CrawlJobListResponse",
    "CrawlJobResponse",
    "CrawlJobUpdate",
    # CrawlLog
    "CrawlLogCreate",
    "CrawlLogFilter",
    "CrawlLogListResponse",
    "CrawlLogResponse",
    # CrawledPage
    "CrawledPageCreate",
    "CrawledPageListResponse",
    "CrawledPageResponse",
    "CrawledPageStats",
    "CrawledPageUpdate",
    # ScheduledJob
    "ScheduledJobCreate",
    "ScheduledJobListResponse",
    "ScheduledJobResponse",
    "ScheduledJobToggleStatus",
    "ScheduledJobUpdate",
    # Website
    "WebsiteCreate",
    "WebsiteListResponse",
    "WebsiteResponse",
    "WebsiteUpdate",
]
