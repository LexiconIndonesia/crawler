"""Database package.

Provides database session management and type-safe query repositories.
Uses sqlc for generating type-safe Python code from SQL queries.

## Usage

```python
from crawler.db import get_db, StatusEnum
from crawler.db.repositories import WebsiteRepository

async with get_db() as session:
    async with session.begin():
        repo = WebsiteRepository(session.connection())
        website = await repo.create(
            name="example",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE
        )
```
"""

from .generated.models import JobTypeEnum, LogLevelEnum, StatusEnum
from .repositories import (
    ContentHashRepository,
    CrawledPageRepository,
    CrawlJobRepository,
    CrawlLogRepository,
    ScheduledJobRepository,
    WebsiteRepository,
)
from .session import engine, get_db

__all__ = [
    "ContentHashRepository",
    "CrawlJobRepository",
    "CrawlLogRepository",
    "CrawledPageRepository",
    "JobTypeEnum",
    "LogLevelEnum",
    "ScheduledJobRepository",
    # Enum types
    "StatusEnum",
    # Repositories
    "WebsiteRepository",
    "engine",
    # Session management
    "get_db",
]
