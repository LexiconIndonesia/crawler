"""Dependency injection providers for API v1."""

from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.api.v1.services import WebsiteService
from crawler.db import get_db
from crawler.db.repositories import ScheduledJobRepository, WebsiteRepository


async def get_website_service(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WebsiteService:
    """Get website service with injected dependencies.

    Args:
        db: Database session from FastAPI dependency

    Returns:
        WebsiteService instance with injected dependencies
    """
    # Get connection from session
    conn = await db.connection()

    # Create repositories
    website_repo = WebsiteRepository(conn)
    scheduled_job_repo = ScheduledJobRepository(conn)

    # Return service with injected repositories
    return WebsiteService(
        website_repo=website_repo,
        scheduled_job_repo=scheduled_job_repo,
    )


# Type aliases for dependency injection
WebsiteServiceDep = Annotated[WebsiteService, Depends(get_website_service)]
