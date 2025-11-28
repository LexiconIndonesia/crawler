"""Database models package.

This package re-exports sqlc-generated Pydantic models for convenience.
All models are generated from SQL queries in sql/queries/*.sql.
"""

# Re-export sqlc-generated models for convenience
from crawler.db.generated.models import (
    ContentHash,
    CrawledPage,
    CrawlJob,
    CrawlLog,
    JobTypeEnum,
    LogLevelEnum,
    StatusEnum,
    Website,
)

__all__ = [
    "ContentHash",
    "CrawlJob",
    "CrawlLog",
    "CrawledPage",
    "JobTypeEnum",
    "LogLevelEnum",
    # Enums
    "StatusEnum",
    # Models
    "Website",
]
