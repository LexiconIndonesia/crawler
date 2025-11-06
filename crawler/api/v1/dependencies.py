"""Dependency injection providers for API v1.

This module provides API v1-specific dependencies that build on top of
the centralized dependencies from crawler.core.dependencies.
"""

from typing import Annotated

from fastapi import Depends

from crawler.api.v1.services import JobService, WebsiteService
from crawler.core.dependencies import DBSessionDep, JobCancellationFlagDep
from crawler.db.repositories import CrawlJobRepository, ScheduledJobRepository, WebsiteRepository


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

    # Return service with injected repositories
    return WebsiteService(
        website_repo=website_repo,
        scheduled_job_repo=scheduled_job_repo,
    )


async def get_job_service(
    db: DBSessionDep,
    cancellation_flag: JobCancellationFlagDep,
) -> JobService:
    """Get job service with injected dependencies.

    Args:
        db: Database session from centralized dependency injection
        cancellation_flag: Job cancellation flag service from centralized dependency injection

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

    # Return service with injected repositories
    return JobService(
        crawl_job_repo=crawl_job_repo,
        website_repo=website_repo,
        cancellation_flag=cancellation_flag,
    )


# Type aliases for dependency injection
WebsiteServiceDep = Annotated[WebsiteService, Depends(get_website_service)]
JobServiceDep = Annotated[JobService, Depends(get_job_service)]
