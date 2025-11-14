"""Dependency injection providers for API v1.

This module provides API v1-specific dependencies that build on top of
the centralized dependencies from crawler.core.dependencies.
"""

from typing import Annotated

from fastapi import Depends

from crawler.api.v1.services import (
    DLQService,
    DuplicateService,
    JobService,
    LogService,
    WebsiteService,
)
from crawler.core.dependencies import DBSessionDep, JobCancellationFlagDep, NATSQueueDep
from crawler.db.repositories import (
    CrawlJobRepository,
    CrawlLogRepository,
    DeadLetterQueueRepository,
    DuplicateGroupRepository,
    ScheduledJobRepository,
    WebsiteConfigHistoryRepository,
    WebsiteRepository,
)


async def get_website_service(
    db: DBSessionDep,
) -> WebsiteService:
    """Get website service with injected dependencies.

    Args:
        db: Database session from centralized dependency injection

    Returns:
        WebsiteService instance with injected repositories

    Usage:
        async def my_route(website_service: WebsiteServiceDep):
            websites = await website_service.list_websites()

    Note:
        This function properly manages database connections from the session's
        connection pool to avoid concurrent operation errors with asyncpg.
    """
    # Get connection from session - this uses the connection pool
    # The connection is managed by the session's transaction context
    conn = await db.connection()

    # Create repositories with the connection
    # Each repository will execute queries sequentially within the transaction
    website_repo = WebsiteRepository(conn)
    scheduled_job_repo = ScheduledJobRepository(conn)
    config_history_repo = WebsiteConfigHistoryRepository(conn)
    crawl_job_repo = CrawlJobRepository(conn)

    # Return service with injected repositories
    return WebsiteService(
        website_repo=website_repo,
        scheduled_job_repo=scheduled_job_repo,
        config_history_repo=config_history_repo,
        crawl_job_repo=crawl_job_repo,
    )


async def get_job_service(
    db: DBSessionDep,
    cancellation_flag: JobCancellationFlagDep,
    nats_queue: NATSQueueDep,
) -> JobService:
    """Get job service with injected dependencies.

    Args:
        db: Database session from centralized dependency injection
        cancellation_flag: Job cancellation flag service from centralized dependency injection
        nats_queue: NATS queue service from centralized dependency injection

    Returns:
        JobService instance with injected repositories and services

    Usage:
        async def my_route(job_service: JobServiceDep):
            job = await job_service.create_seed_job(request)

    Note:
        This function properly manages database connections from the session's
        connection pool to avoid concurrent operation errors with asyncpg.
    """
    # Get connection from session - this uses the connection pool
    # The connection is managed by the session's transaction context
    conn = await db.connection()

    # Create repositories with the connection
    # Each repository will execute queries sequentially within the transaction
    crawl_job_repo = CrawlJobRepository(conn)
    website_repo = WebsiteRepository(conn)

    # Return service with injected repositories and services
    return JobService(
        crawl_job_repo=crawl_job_repo,
        website_repo=website_repo,
        cancellation_flag=cancellation_flag,
        nats_queue=nats_queue,
    )


async def get_log_service(
    db: DBSessionDep,
) -> LogService:
    """Get log service with injected dependencies.

    Args:
        db: Database session from centralized dependency injection

    Returns:
        LogService instance with injected repositories

    Usage:
        async def my_route(log_service: LogServiceDep):
            logs = await log_service.get_job_logs(job_id)

    Note:
        This function properly manages database connections from the session's
        connection pool to avoid concurrent operation errors with asyncpg.
    """
    # Get connection from session - this uses the connection pool
    # The connection is managed by the session's transaction context
    conn = await db.connection()

    # Create repositories with the connection
    # Each repository will execute queries sequentially within the transaction
    crawl_log_repo = CrawlLogRepository(conn)
    crawl_job_repo = CrawlJobRepository(conn)

    # Return service with injected repositories
    return LogService(
        crawl_log_repo=crawl_log_repo,
        crawl_job_repo=crawl_job_repo,
    )


async def get_duplicate_service(
    db: DBSessionDep,
) -> DuplicateService:
    """Get duplicate service with injected dependencies.

    Args:
        db: Database session from centralized dependency injection

    Returns:
        DuplicateService instance with injected repositories

    Usage:
        async def my_route(duplicate_service: DuplicateServiceDep):
            canonical = await duplicate_service.get_canonical_for_duplicate(page_id)

    Note:
        This function properly manages database connections from the session's
        connection pool to avoid concurrent operation errors with asyncpg.
    """
    # Get connection from session - this uses the connection pool
    # The connection is managed by the session's transaction context
    conn = await db.connection()

    # Create repositories with the connection
    # Each repository will execute queries sequentially within the transaction
    duplicate_repo = DuplicateGroupRepository(conn)

    # Return service with injected repositories
    return DuplicateService(duplicate_repo=duplicate_repo)


async def get_dlq_service(
    db: DBSessionDep,
) -> DLQService:
    """Get DLQ service with injected dependencies.

    Args:
        db: Database session from centralized dependency injection

    Returns:
        DLQService instance with injected repositories

    Usage:
        async def my_route(dlq_service: DLQServiceDep):
            entries = await dlq_service.list_entries()

    Note:
        This function properly manages database connections from the session's
        connection pool to avoid concurrent operation errors with asyncpg.
    """
    # Get connection from session - this uses the connection pool
    # The connection is managed by the session's transaction context
    conn = await db.connection()

    # Create repositories with the connection
    # Each repository will execute queries sequentially within the transaction
    dlq_repo = DeadLetterQueueRepository(conn)
    crawl_job_repo = CrawlJobRepository(conn)

    # Return service with injected repositories
    return DLQService(
        dlq_repo=dlq_repo,
        crawl_job_repo=crawl_job_repo,
    )


# Type aliases for dependency injection
WebsiteServiceDep = Annotated[WebsiteService, Depends(get_website_service)]
JobServiceDep = Annotated[JobService, Depends(get_job_service)]
LogServiceDep = Annotated[LogService, Depends(get_log_service)]
DuplicateServiceDep = Annotated[DuplicateService, Depends(get_duplicate_service)]
DLQServiceDep = Annotated[DLQService, Depends(get_dlq_service)]
