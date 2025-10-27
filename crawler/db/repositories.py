"""Database repositories using sqlc-generated queries.

Provides clean interfaces to sqlc-generated database queries.
All queries are type-safe and validated at generation time.

Repository methods use exact types from sqlc-generated code for type safety.
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import (
    content_hash,
    crawl_job,
    crawl_log,
    crawled_page,
    models,
    scheduled_job,
    website,
)
from crawler.db.generated.crawled_page import CreateCrawledPageParams
from crawler.db.generated.models import LogLevelEnum, StatusEnum


def _to_uuid(value: str | UUID) -> UUID:
    """Convert string to UUID if needed."""
    if isinstance(value, UUID):
        return value
    return UUID(value)


def _to_uuid_optional(value: str | UUID | None) -> UUID | None:
    """Convert string to UUID if needed, handling None."""
    if value is None:
        return None
    return _to_uuid(value)


class WebsiteRepository:
    """Repository for website operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = website.AsyncQuerier(connection)

    async def create(
        self,
        name: str,
        base_url: str,
        config: dict[str, Any],
        cron_schedule: str | None = None,
        created_by: str | None = None,
        status: Any | None = None,
    ) -> models.Website | None:
        """Create a new website.

        Args:
            name: Website name
            base_url: Base URL
            config: Configuration dict (will be serialized to JSON)
            cron_schedule: Optional cron schedule (uses default if None)
            created_by: Optional creator identifier
            status: Optional status (uses 'active' default if None)

        Returns:
            Created Website model or None
        """
        return await self._querier.create_website(
            name=name,
            base_url=base_url,
            config=json.dumps(config),
            cron_schedule=cron_schedule,
            created_by=created_by,
            status=status,
        )

    async def get_by_id(self, website_id: str | UUID) -> models.Website | None:
        """Get website by ID."""
        return await self._querier.get_website_by_id(id=_to_uuid(website_id))

    async def get_by_name(self, name: str) -> models.Website | None:
        """Get website by name."""
        return await self._querier.get_website_by_name(name=name)

    async def list(
        self, status: StatusEnum | None = None, limit: int = 100, offset: int = 0
    ) -> list[models.Website]:
        """List websites with pagination.

        Args:
            status: Optional status filter (None returns all)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Website models

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        websites = []
        # sqlc generates non-optional but SQL supports COALESCE (optional filter)
        async for website_obj in self._querier.list_websites(
            status=status,  # type: ignore[arg-type]
            limit_count=limit,
            offset_count=offset,
        ):
            websites.append(website_obj)
        return websites

    async def count(self, status: StatusEnum | None = None) -> int:
        """Count websites.

        Args:
            status: Optional status filter (None counts all)

        Returns:
            Count of websites

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        # sqlc generates non-optional but SQL supports COALESCE (optional filter)
        result = await self._querier.count_websites(status=status)  # type: ignore[arg-type]
        return result if result is not None else 0

    async def update(
        self,
        website_id: str | UUID,
        name: str | None = None,
        base_url: str | None = None,
        config: dict[str, Any] | None = None,
        cron_schedule: str | None = None,
        status: StatusEnum | None = None,
    ) -> models.Website | None:
        """Update website fields.

        Args:
            website_id: Website ID
            name: New name (optional, uses existing if None)
            base_url: New base URL (optional, uses existing if None)
            config: New config dict (optional, uses existing if None, will be serialized to JSON)
            cron_schedule: New cron schedule (optional, uses existing if None)
            status: New status (optional, uses existing if None)

        Returns:
            Updated Website model or None

        Note:
            SQL uses COALESCE for all parameters, but sqlc generates non-optional types.
            We accept Optional here to match the SQL behavior.
        """
        # sqlc generates non-optional types but SQL supports COALESCE (optional updates)
        return await self._querier.update_website(  # type: ignore[arg-type]
            id=_to_uuid(website_id),
            name=name,  # type: ignore[arg-type]
            base_url=base_url,  # type: ignore[arg-type]
            config=json.dumps(config) if config else None,
            cron_schedule=cron_schedule,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
        )

    async def delete(self, website_id: str | UUID) -> None:
        """Delete website."""
        await self._querier.delete_website(id=_to_uuid(website_id))


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
        website_id: str | UUID,
        seed_url: str,
        job_type: Any | None = None,
        embedded_config: dict[str, Any] | None = None,
        priority: Any | None = None,
        scheduled_at: datetime | None = None,
        max_retries: Any | None = None,
        metadata: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a new crawl job.

        Args:
            website_id: Website ID
            seed_url: Seed URL to start crawling
            job_type: Optional job type (uses 'one_time' default if None)
            embedded_config: Optional embedded config dict (will be serialized to JSON)
            priority: Optional priority (uses 5 default if None)
            scheduled_at: Optional scheduled time
            max_retries: Optional max retries (uses 3 default if None)
            metadata: Optional metadata dict (will be serialized to JSON)
            variables: Optional variables dict (will be serialized to JSON)

        Returns:
            Created CrawlJob model or None
        """
        return await self._querier.create_crawl_job(
            website_id=_to_uuid(website_id),
            job_type=job_type,
            seed_url=seed_url,
            embedded_config=json.dumps(embedded_config) if embedded_config else None,
            priority=priority,
            scheduled_at=scheduled_at,
            max_retries=max_retries,
            metadata=json.dumps(metadata) if metadata else None,
            variables=json.dumps(variables) if variables else None,
        )

    async def get_by_id(self, job_id: str | UUID) -> models.CrawlJob | None:
        """Get crawl job by ID."""
        return await self._querier.get_crawl_job_by_id(id=_to_uuid(job_id))

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
            id=_to_uuid(job_id),
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
            id=_to_uuid(job_id), progress=json.dumps(progress) if progress else None
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
            id=_to_uuid(job_id), cancelled_by=cancelled_by, cancellation_reason=reason
        )


class CrawledPageRepository:
    """Repository for crawled page operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = crawled_page.AsyncQuerier(connection)

    async def create(
        self,
        website_id: str | UUID,
        job_id: str | UUID,
        url: str,
        url_hash: str,
        content_hash: str,
        crawled_at: datetime,
        title: str | None = None,
        extracted_content: str | None = None,
        metadata: dict[str, Any] | None = None,
        gcs_html_path: str | None = None,
        gcs_documents: dict[str, Any] | None = None,
    ) -> models.CrawledPage | None:
        """Create a new crawled page record.

        Args:
            website_id: Website ID
            job_id: Job ID
            url: Page URL
            url_hash: URL hash for deduplication
            content_hash: Content hash for duplicate detection
            crawled_at: Timestamp when page was crawled
            title: Optional page title
            extracted_content: Optional extracted text content
            metadata: Optional metadata dict (will be serialized to JSON)
            gcs_html_path: Optional GCS path to stored HTML
            gcs_documents: Optional GCS documents dict (will be serialized to JSON)

        Returns:
            Created CrawledPage model or None
        """
        params = CreateCrawledPageParams(
            website_id=_to_uuid(website_id),
            job_id=_to_uuid(job_id),
            url=url,
            url_hash=url_hash,
            content_hash=content_hash,
            title=title,
            extracted_content=extracted_content,
            metadata=json.dumps(metadata) if metadata else None,
            gcs_html_path=gcs_html_path,
            gcs_documents=json.dumps(gcs_documents) if gcs_documents else None,
            crawled_at=crawled_at,
        )
        return await self._querier.create_crawled_page(params)

    async def get_by_id(self, page_id: str | UUID) -> models.CrawledPage | None:
        """Get page by ID."""
        return await self._querier.get_crawled_page_by_id(id=_to_uuid(page_id))

    async def get_by_url_hash(
        self, website_id: str | UUID, url_hash: str
    ) -> models.CrawledPage | None:
        """Get page by URL hash."""
        return await self._querier.get_page_by_url_hash(
            website_id=_to_uuid(website_id), url_hash=url_hash
        )

    async def list_by_job(
        self, job_id: str | UUID, limit: int = 100, offset: int = 0
    ) -> list[models.CrawledPage]:
        """List pages for a job."""
        pages = []
        async for page in self._querier.list_pages_by_job(
            job_id=_to_uuid(job_id), limit_count=limit, offset_count=offset
        ):
            pages.append(page)
        return pages

    async def mark_as_duplicate(
        self,
        page_id: str | UUID,
        duplicate_of: str | UUID | None,
        similarity_score: int | None = None,
    ) -> models.CrawledPage | None:
        """Mark page as duplicate.

        Args:
            page_id: Page ID
            duplicate_of: ID of the original page (optional per sqlc)
            similarity_score: Optional similarity score

        Returns:
            Updated CrawledPage model or None
        """
        return await self._querier.mark_page_as_duplicate(
            id=_to_uuid(page_id),
            duplicate_of=_to_uuid_optional(duplicate_of),
            similarity_score=similarity_score,
        )


class ContentHashRepository:
    """Repository for content hash operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = content_hash.AsyncQuerier(connection)

    async def upsert(
        self, content_hash_value: str, first_seen_page_id: str | UUID | None
    ) -> models.ContentHash | None:
        """Insert or update content hash (increments count if exists).

        Args:
            content_hash_value: Content hash string
            first_seen_page_id: Optional ID of first page with this content

        Returns:
            ContentHash model or None
        """
        return await self._querier.upsert_content_hash(
            content_hash=content_hash_value,
            first_seen_page_id=_to_uuid_optional(first_seen_page_id),
        )

    async def get(self, content_hash_value: str) -> models.ContentHash | None:
        """Get content hash record."""
        return await self._querier.get_content_hash(content_hash=content_hash_value)


class CrawlLogRepository:
    """Repository for crawl log operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = crawl_log.AsyncQuerier(connection)

    async def create(
        self,
        job_id: str | UUID,
        website_id: str | UUID,
        message: str,
        log_level: LogLevelEnum | None = None,
        step_name: str | None = None,
        context: dict[str, Any] | None = None,
        trace_id: str | UUID | None = None,
    ) -> models.CrawlLog | None:
        """Create a new log entry.

        Args:
            job_id: Job ID
            website_id: Website ID
            message: Log message
            log_level: Optional log level (uses 'INFO' default if None)
            step_name: Optional step name
            context: Optional context dict (will be serialized to JSON)
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Created CrawlLog model or None

        Note:
            SQL uses COALESCE for log_level, but sqlc generates non-optional type.
        """
        # sqlc generates non-optional but SQL supports COALESCE (optional with default)
        return await self._querier.create_crawl_log(
            job_id=_to_uuid(job_id),
            website_id=_to_uuid(website_id),
            step_name=step_name,
            log_level=log_level,  # type: ignore[arg-type]
            message=message,
            context=json.dumps(context) if context else None,
            trace_id=_to_uuid_optional(trace_id),
        )

    async def list_by_job(
        self,
        job_id: str | UUID,
        log_level: LogLevelEnum | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[models.CrawlLog]:
        """List logs for a job.

        Args:
            job_id: Job ID
            log_level: Optional log level filter (None returns all levels)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of CrawlLog models

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        logs = []
        # sqlc generates non-optional but SQL supports COALESCE (optional filter)
        async for log in self._querier.list_logs_by_job(
            job_id=_to_uuid(job_id),
            log_level=log_level,  # type: ignore[arg-type]
            limit_count=limit,
            offset_count=offset,
        ):
            logs.append(log)
        return logs

    async def get_errors(self, job_id: str | UUID, limit: int = 100) -> list[models.CrawlLog]:
        """Get error logs for a job."""
        logs = []
        async for log in self._querier.get_error_logs(job_id=_to_uuid(job_id), limit_count=limit):
            logs.append(log)
        return logs


class ScheduledJobRepository:
    """Repository for scheduled job operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = scheduled_job.AsyncQuerier(connection)

    @staticmethod
    def _deserialize_job_config(job: models.ScheduledJob | None) -> models.ScheduledJob | None:
        """Deserialize job_config from JSON string to dict.

        Args:
            job: ScheduledJob model from database

        Returns:
            ScheduledJob with deserialized job_config, or None if input is None
        """
        if job is None:
            return None

        # If job_config is a string, deserialize it
        if isinstance(job.job_config, str):
            try:
                deserialized_config = json.loads(job.job_config)
                # Create a new model with deserialized config
                return job.model_copy(update={"job_config": deserialized_config})
            except (json.JSONDecodeError, TypeError):
                # If deserialization fails, keep original value
                return job

        return job

    async def create(
        self,
        website_id: str | UUID,
        cron_schedule: str,
        next_run_time: datetime,
        is_active: bool | None = None,
        job_config: dict[str, Any] | None = None,
    ) -> models.ScheduledJob | None:
        """Create a new scheduled job.

        Args:
            website_id: Website ID
            cron_schedule: Cron expression for schedule
            next_run_time: Next scheduled execution time
            is_active: Optional active flag (uses true default if None)
            job_config: Optional job config dict (will be serialized to JSON)

        Returns:
            Created ScheduledJob model or None
        """
        return await self._querier.create_scheduled_job(
            website_id=_to_uuid(website_id),
            cron_schedule=cron_schedule,
            next_run_time=next_run_time,
            is_active=is_active,
            job_config=json.dumps(job_config) if job_config else None,
        )

    async def get_by_id(self, job_id: str | UUID) -> models.ScheduledJob | None:
        """Get scheduled job by ID with deserialized job_config."""
        job = await self._querier.get_scheduled_job_by_id(id=_to_uuid(job_id))
        return self._deserialize_job_config(job)

    async def get_by_website_id(self, website_id: str | UUID) -> list[models.ScheduledJob]:
        """Get all scheduled jobs for a website with deserialized job_config."""
        jobs = []
        async for job in self._querier.get_scheduled_jobs_by_website_id(
            website_id=_to_uuid(website_id)
        ):
            deserialized_job = self._deserialize_job_config(job)
            if deserialized_job:
                jobs.append(deserialized_job)
        return jobs

    async def list_active(self, limit: int = 100, offset: int = 0) -> list[models.ScheduledJob]:
        """List active scheduled jobs with deserialized job_config."""
        jobs = []
        async for job in self._querier.list_active_scheduled_jobs(
            offset_count=offset, limit_count=limit
        ):
            deserialized_job = self._deserialize_job_config(job)
            if deserialized_job:
                jobs.append(deserialized_job)
        return jobs

    async def get_due_jobs(
        self, cutoff_time: datetime, limit: int = 100
    ) -> list[models.ScheduledJob]:
        """Get jobs due for execution with deserialized job_config.

        Args:
            cutoff_time: Jobs with next_run_time <= this time will be returned
            limit: Maximum number of jobs to return

        Returns:
            List of ScheduledJob models with deserialized job_config, ordered by next_run_time
        """
        jobs = []
        async for job in self._querier.get_jobs_due_for_execution(
            cutoff_time=cutoff_time, limit_count=limit
        ):
            deserialized_job = self._deserialize_job_config(job)
            if deserialized_job:
                jobs.append(deserialized_job)
        return jobs

    async def update(
        self,
        job_id: str | UUID,
        cron_schedule: str | None = None,
        next_run_time: datetime | None = None,
        last_run_time: datetime | None = None,
        is_active: bool | None = None,
        job_config: dict[str, Any] | None = None,
    ) -> models.ScheduledJob | None:
        """Update scheduled job fields.

        Args:
            job_id: Job ID
            cron_schedule: New cron schedule (optional, uses existing if None)
            next_run_time: New next run time (optional, uses existing if None)
            last_run_time: New last run time (optional, uses existing if None)
            is_active: New active flag (optional, uses existing if None)
            job_config: New config dict (optional, uses existing if None,
                will be serialized to JSON)

        Returns:
            Updated ScheduledJob model or None

        Note:
            SQL uses COALESCE for all parameters, but sqlc generates non-optional types.
        """
        # sqlc generates non-optional types but SQL supports COALESCE (optional updates)
        return await self._querier.update_scheduled_job(  # type: ignore[arg-type]
            id=_to_uuid(job_id),
            cron_schedule=cron_schedule,  # type: ignore[arg-type]
            next_run_time=next_run_time,  # type: ignore[arg-type]
            last_run_time=last_run_time,
            is_active=is_active,  # type: ignore[arg-type]
            job_config=json.dumps(job_config) if job_config else None,
        )

    async def update_next_run(
        self,
        job_id: str | UUID,
        next_run_time: datetime,
        last_run_time: datetime | None = None,
    ) -> models.ScheduledJob | None:
        """Update next run time after execution.

        Args:
            job_id: Job ID
            next_run_time: Next scheduled execution time
            last_run_time: Optional last execution time

        Returns:
            Updated ScheduledJob model or None
        """
        return await self._querier.update_scheduled_job_next_run(
            id=_to_uuid(job_id), next_run_time=next_run_time, last_run_time=last_run_time
        )

    async def toggle_status(
        self, job_id: str | UUID, is_active: bool
    ) -> models.ScheduledJob | None:
        """Toggle scheduled job active status.

        Args:
            job_id: Job ID
            is_active: New active status

        Returns:
            Updated ScheduledJob model or None
        """
        return await self._querier.toggle_scheduled_job_status(
            id=_to_uuid(job_id), is_active=is_active
        )

    async def delete(self, job_id: str | UUID) -> None:
        """Delete scheduled job."""
        await self._querier.delete_scheduled_job(id=_to_uuid(job_id))

    async def count(
        self, website_id: str | UUID | None = None, is_active: bool | None = None
    ) -> int:
        """Count scheduled jobs.

        Args:
            website_id: Optional website filter (None counts all websites)
            is_active: Optional active filter (None counts all statuses)

        Returns:
            Count of scheduled jobs

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        # sqlc generates non-optional but SQL supports COALESCE (optional filter)
        result = await self._querier.count_scheduled_jobs(
            website_id=_to_uuid(website_id) if website_id else None,  # type: ignore[arg-type]
            is_active=is_active,  # type: ignore[arg-type]
        )
        return result if result is not None else 0
