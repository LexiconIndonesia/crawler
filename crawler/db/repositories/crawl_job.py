"""Crawl job repository using sqlc-generated queries."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import crawl_job, models
from crawler.db.generated.models import StatusEnum

from .base import to_uuid, to_uuid_optional


class CrawlJobRepository:
    """Repository for crawl job operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = crawl_job.AsyncQuerier(connection)

    async def create(
        self,
        seed_url: str,
        website_id: str | UUID | None = None,
        job_type: Any | None = None,
        inline_config: dict[str, Any] | None = None,
        priority: Any | None = None,
        scheduled_at: datetime | None = None,
        max_retries: Any | None = None,
        metadata: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a new crawl job.

        Args:
            seed_url: Seed URL to start crawling (required)
            website_id: Optional website ID for template-based jobs
            job_type: Optional job type (uses 'one_time' default if None)
            inline_config: Optional inline config dict (will be serialized to JSON)
            priority: Optional priority (uses 5 default if None)
            scheduled_at: Optional scheduled time
            max_retries: Optional max retries (uses 3 default if None)
            metadata: Optional metadata dict (will be serialized to JSON)
            variables: Optional variables dict (will be serialized to JSON)

        Returns:
            Created CrawlJob model or None

        Note:
            Either website_id or inline_config must be provided.
        """
        return await self._querier.create_crawl_job(
            website_id=to_uuid_optional(website_id),
            job_type=job_type,
            seed_url=seed_url,
            inline_config=json.dumps(inline_config) if inline_config else None,
            priority=priority,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            metadata=json.dumps(metadata) if metadata else None,
            variables=json.dumps(variables) if variables else None,
        )

    async def get_by_id(self, job_id: str | UUID) -> models.CrawlJob | None:
        """Get crawl job by ID."""
        return await self._querier.get_crawl_job_by_id(id=to_uuid(job_id))

    async def get_pending(self, limit: int = 100) -> list[models.CrawlJob]:
        """Get pending jobs ordered by priority."""
        jobs = []
        async for job in self._querier.get_pending_jobs(limit_count=limit):
            jobs.append(job)
        return jobs

    async def update_status(
        self,
        job_id: str | UUID,
        status: StatusEnum,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> models.CrawlJob | None:
        """Update job status.

        Args:
            job_id: Job ID
            status: New status (required StatusEnum)
            started_at: Optional started timestamp
            completed_at: Optional completed timestamp
            error_message: Optional error message

        Returns:
            Updated CrawlJob model or None
        """
        return await self._querier.update_crawl_job_status(
            id=to_uuid(job_id),
            status=status,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
        )

    async def update_progress(
        self, job_id: str | UUID, progress: dict[str, Any] | None
    ) -> models.CrawlJob | None:
        """Update job progress.

        Args:
            job_id: Job ID
            progress: Progress data dict (will be serialized to JSON)

        Returns:
            Updated CrawlJob model or None
        """
        return await self._querier.update_crawl_job_progress(
            id=to_uuid(job_id), progress=json.dumps(progress) if progress else None
        )

    async def cancel(
        self, job_id: str | UUID, cancelled_by: str | None, reason: str | None = None
    ) -> models.CrawlJob | None:
        """Cancel a job.

        Args:
            job_id: Job ID
            cancelled_by: Optional canceller identifier
            reason: Optional cancellation reason

        Returns:
            Cancelled CrawlJob model or None
        """
        return await self._querier.cancel_crawl_job(
            id=to_uuid(job_id), cancelled_by=cancelled_by, cancellation_reason=reason
        )

    async def get_inline_config_jobs(
        self, limit: int = 100, offset: int = 0
    ) -> list[models.CrawlJob]:
        """Get jobs that use inline configuration (no website template).

        Args:
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of CrawlJob models with inline configs
        """
        jobs = []
        async for job in self._querier.get_inline_config_jobs(
            limit_count=limit, offset_count=offset
        ):
            jobs.append(job)
        return jobs

    async def get_by_seed_url(
        self, seed_url: str, limit: int = 100, offset: int = 0
    ) -> list[models.CrawlJob]:
        """Get jobs for a specific seed URL.

        Args:
            seed_url: Seed URL to filter by
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of CrawlJob models
        """
        jobs = []
        async for job in self._querier.get_jobs_by_seed_url(
            seed_url=seed_url, limit_count=limit, offset_count=offset
        ):
            jobs.append(job)
        return jobs

    async def create_seed_url_submission(
        self,
        seed_url: str,
        inline_config: dict[str, Any],
        variables: dict[str, Any] | None = None,
        job_type: Any | None = None,
        priority: Any | None = None,
        scheduled_at: datetime | None = None,
        max_retries: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a job with inline configuration (seed URL submission without website template).

        Args:
            seed_url: Seed URL to start crawling
            inline_config: Inline configuration dict (required, will be serialized to JSON)
            variables: Optional variables dict (will be serialized to JSON)
            job_type: Optional job type (uses 'one_time' default if None)
            priority: Optional priority (uses 5 default if None)
            scheduled_at: Optional scheduled time
            max_retries: Optional max retries (uses 3 default if None)
            metadata: Optional metadata dict (will be serialized to JSON)

        Returns:
            Created CrawlJob model or None
        """
        return await self._querier.create_seed_url_submission(
            seed_url=seed_url,
            inline_config=json.dumps(inline_config),
            variables=json.dumps(variables) if variables else None,
            job_type=job_type,
            priority=priority,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            metadata=json.dumps(metadata) if metadata else None,
        )

    async def create_template_based_job(
        self,
        website_id: str | UUID,
        seed_url: str,
        variables: dict[str, Any] | None = None,
        job_type: Any | None = None,
        priority: Any | None = None,
        scheduled_at: datetime | None = None,
        max_retries: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a job using a website template configuration.

        Args:
            website_id: Website ID (required)
            seed_url: Seed URL to start crawling
            variables: Optional variables dict (will be serialized to JSON)
            job_type: Optional job type (uses 'one_time' default if None)
            priority: Optional priority (uses 5 default if None)
            scheduled_at: Optional scheduled time
            max_retries: Optional max retries (uses 3 default if None)
            metadata: Optional metadata dict (will be serialized to JSON)

        Returns:
            Created CrawlJob model or None
        """
        return await self._querier.create_template_based_job(
            website_id=to_uuid(website_id),
            seed_url=seed_url,
            variables=json.dumps(variables) if variables else None,
            job_type=job_type,
            priority=priority,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            metadata=json.dumps(metadata) if metadata else None,
        )
