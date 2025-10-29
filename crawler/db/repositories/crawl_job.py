"""Crawl job repository using sqlc-generated queries."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import crawl_job, models
from crawler.db.generated.models import JobTypeEnum, StatusEnum

from .base import to_uuid


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
        job_type: JobTypeEnum = JobTypeEnum.ONE_TIME,
        inline_config: dict[str, Any] | None = None,
        priority: int = 5,
        scheduled_at: datetime | None = None,
        max_retries: int = 3,
        metadata: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a new crawl job (dispatcher method).

        This method acts as a dispatcher that validates input and delegates
        to the appropriate specialized creation method based on the provided
        parameters.

        **Important**: Exactly one of `website_id` or `inline_config` must be
        provided (mutually exclusive). This determines which job creation method
        is used.

        Args:
            seed_url: Seed URL to start crawling (required)
            website_id: Website ID for template-based jobs (mutually exclusive with inline_config)
            job_type: Job type enum (defaults to ONE_TIME)
            inline_config: Inline config dict for one-off jobs (mutually exclusive with website_id)
            priority: Priority level (defaults to 5)
            scheduled_at: Optional scheduled time
            max_retries: Maximum retry attempts (defaults to 3)
            metadata: Optional metadata dict (will be serialized to JSON)
            variables: Optional variables dict (will be serialized to JSON)

        Returns:
            Created CrawlJob model or None

        Raises:
            ValueError: If both `website_id` and `inline_config` are provided,
                       or if neither is provided. Exactly one must be specified.

        Note:
            - If `website_id` is provided → dispatches to `create_template_based_job()`
            - If `inline_config` is provided → dispatches to `create_seed_url_submission()`
        """
        # Validate mutual exclusivity at application level
        has_website_id = website_id is not None
        has_inline_config = inline_config is not None

        if has_website_id and has_inline_config:
            raise ValueError(
                "Cannot specify both 'website_id' and 'inline_config' (mutually exclusive). "
                "Choose one approach:\n"
                "  • For jobs using a website template, call: "
                "create_template_based_job(website_id=..., seed_url=...)\n"
                "  • For one-off jobs with inline config, call: "
                "create_seed_url_submission(seed_url=..., inline_config=...)"
            )

        if not has_website_id and not has_inline_config:
            raise ValueError(
                "Must specify exactly one of 'website_id' or 'inline_config'. "
                "Choose the appropriate method:\n"
                "  • For jobs using a website template → "
                "create_template_based_job(website_id=..., seed_url=...)\n"
                "  • For one-off jobs with custom config → "
                "create_seed_url_submission(seed_url=..., inline_config=...)"
            )

        # Dispatch to appropriate specialized method
        if has_website_id:
            # Type narrowing: website_id is guaranteed to be str | UUID here
            assert website_id is not None
            return await self.create_template_based_job(
                website_id=website_id,
                seed_url=seed_url,
                variables=variables,
                job_type=job_type,
                priority=priority,
                scheduled_at=scheduled_at,
                max_retries=max_retries,
                metadata=metadata,
            )
        else:
            # Type narrowing: inline_config is guaranteed to be dict here
            assert inline_config is not None
            return await self.create_seed_url_submission(
                seed_url=seed_url,
                inline_config=inline_config,
                variables=variables,
                job_type=job_type,
                priority=priority,
                scheduled_at=scheduled_at,
                max_retries=max_retries,
                metadata=metadata,
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
        job_type: JobTypeEnum = JobTypeEnum.ONE_TIME,
        priority: int = 5,
        scheduled_at: datetime | None = None,
        max_retries: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a job with inline configuration (seed URL submission without website template).

        Args:
            seed_url: Seed URL to start crawling
            inline_config: Inline configuration dict (required, will be serialized to JSON)
            variables: Optional variables dict (will be serialized to JSON)
            job_type: Job type enum (defaults to ONE_TIME)
            priority: Priority level (defaults to 5)
            scheduled_at: Optional scheduled time
            max_retries: Maximum retry attempts (defaults to 3)
            metadata: Optional metadata dict (will be serialized to JSON)

        Returns:
            Created CrawlJob model or None

        Raises:
            ValueError: If inline_config is None or empty.
        """
        # Validate that inline_config is provided
        if not inline_config:
            raise ValueError(
                "Missing required parameter 'inline_config' for seed URL submission. "
                "You must provide crawl configuration. Choose one approach:\n"
                "  • Provide inline_config with crawl settings:\n"
                "    Example: inline_config={'method': 'api', 'max_depth': 3, 'timeout': 30}\n"
                "  • Or use a website template instead:\n"
                "    Call create_template_based_job(website_id=..., seed_url=...) "
                "to use pre-configured settings"
            )

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
        job_type: JobTypeEnum = JobTypeEnum.ONE_TIME,
        priority: int = 5,
        scheduled_at: datetime | None = None,
        max_retries: int = 3,
        metadata: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a job using a website template configuration.

        Args:
            website_id: Website ID (required)
            seed_url: Seed URL to start crawling
            variables: Optional variables dict (will be serialized to JSON)
            job_type: Job type enum (defaults to ONE_TIME)
            priority: Priority level (defaults to 5)
            scheduled_at: Optional scheduled time
            max_retries: Maximum retry attempts (defaults to 3)
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
