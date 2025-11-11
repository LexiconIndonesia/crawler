"""Database repositories using sqlc-generated queries.

This module provides clean interfaces to sqlc-generated database queries.
All queries are type-safe and validated at generation time.

Repository classes:
    - WebsiteRepository: Website CRUD operations
    - CrawlJobRepository: Crawl job management
    - CrawledPageRepository: Crawled page tracking
    - ContentHashRepository: Content deduplication
    - CrawlLogRepository: Crawl logging
    - ScheduledJobRepository: Scheduled job management
    - WebsiteConfigHistoryRepository: Website configuration history
    - DuplicateGroupRepository: Duplicate group and relationship management
"""

from .content_hash import ContentHashRepository
from .crawl_job import CrawlJobRepository
from .crawl_log import CrawlLogRepository
from .crawled_page import CrawledPageRepository
from .duplicate_group import DuplicateGroupRepository
from .scheduled_job import ScheduledJobRepository
from .website import WebsiteRepository
from .website_config_history import WebsiteConfigHistoryRepository

__all__ = [
    "ContentHashRepository",
    "CrawlJobRepository",
    "CrawlLogRepository",
    "CrawledPageRepository",
    "DuplicateGroupRepository",
    "ScheduledJobRepository",
    "WebsiteConfigHistoryRepository",
    "WebsiteRepository",
]
