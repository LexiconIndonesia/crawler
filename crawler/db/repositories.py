"""Database repositories using sqlc-generated queries.

Provides clean interfaces to sqlc-generated database queries.
All queries are type-safe and validated at generation time.
"""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import content_hash, crawl_job, crawl_log, crawled_page, models, website
from crawler.db.generated.crawled_page import CreateCrawledPageParams
from crawler.db.generated.models import JobTypeEnum, LogLevelEnum, StatusEnum


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


def _ensure_status_enum(value: str | StatusEnum | None) -> StatusEnum | None:
    """Convert string to StatusEnum if needed."""
    if value is None:
        return None
    if isinstance(value, StatusEnum):
        return value
    return StatusEnum(value)


def _ensure_job_type_enum(value: str | JobTypeEnum | None) -> JobTypeEnum | None:
    """Convert string to JobTypeEnum if needed."""
    if value is None:
        return None
    if isinstance(value, JobTypeEnum):
        return value
    return JobTypeEnum(value)


def _ensure_log_level_enum(value: str | LogLevelEnum | None) -> LogLevelEnum | None:
    """Convert string to LogLevelEnum if needed."""
    if value is None:
        return None
    if isinstance(value, LogLevelEnum):
        return value
    return LogLevelEnum(value)


class WebsiteRepository:
    """Repository for website operations."""

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
        created_by: str | None = None,
        status: str | StatusEnum | None = None,
    ) -> models.Website | None:
        """Create a new website."""
        status_enum = _ensure_status_enum(status)
        return await self._querier.create_website(
            name=name,
            base_url=base_url,
            config=json.dumps(config),
            created_by=created_by,
            status=status_enum,
        )

    async def get_by_id(self, website_id: str | UUID) -> models.Website | None:
        """Get website by ID."""
        return await self._querier.get_website_by_id(id=_to_uuid(website_id))

    async def get_by_name(self, name: str) -> models.Website | None:
        """Get website by name."""
        return await self._querier.get_website_by_name(name=name)

    async def list(
        self, status: str | StatusEnum | None = None, limit: int = 100, offset: int = 0
    ) -> list[models.Website]:
        """List websites with pagination."""
        status_enum = _ensure_status_enum(status)
        websites = []
        async for website_obj in self._querier.list_websites(
            status=status_enum,  # type: ignore[arg-type]
            limit_count=limit,
            offset_count=offset,
        ):
            websites.append(website_obj)
        return websites

    async def count(self, status: str | StatusEnum | None = None) -> int:
        """Count websites."""
        status_enum = _ensure_status_enum(status)
        result = await self._querier.count_websites(status=status_enum)  # type: ignore[arg-type]
        return result if result is not None else 0

    async def update(
        self,
        website_id: str | UUID,
        name: str | None = None,
        base_url: str | None = None,
        config: dict[str, Any] | None = None,
        status: str | StatusEnum | None = None,
    ) -> models.Website | None:
        """Update website."""
        status_enum = _ensure_status_enum(status)
        return await self._querier.update_website(
            id=_to_uuid(website_id),
            name=name,  # type: ignore[arg-type]
            base_url=base_url,  # type: ignore[arg-type]
            config=json.dumps(config) if config else None,
            status=status_enum,  # type: ignore[arg-type]
        )

    async def delete(self, website_id: str | UUID) -> None:
        """Delete website."""
        await self._querier.delete_website(id=_to_uuid(website_id))


class CrawlJobRepository:
    """Repository for crawl job operations."""

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
        job_type: str | JobTypeEnum | None = None,
        embedded_config: dict[str, Any] | None = None,
        priority: int | None = None,
        scheduled_at: datetime | None = None,
        max_retries: int | None = None,
        metadata: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> models.CrawlJob | None:
        """Create a new crawl job."""
        job_type_enum = _ensure_job_type_enum(job_type)
        return await self._querier.create_crawl_job(
            website_id=_to_uuid(website_id),
            job_type=job_type_enum,
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
        status: str | StatusEnum,
        started_at: datetime | None = None,
        completed_at: datetime | None = None,
        error_message: str | None = None,
    ) -> models.CrawlJob | None:
        """Update job status."""
        status_enum = _ensure_status_enum(status)
        return await self._querier.update_crawl_job_status(
            id=_to_uuid(job_id),
            status=status_enum,  # type: ignore[arg-type]
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
        )

    async def update_progress(
        self, job_id: str | UUID, progress: dict[str, Any]
    ) -> models.CrawlJob | None:
        """Update job progress."""
        return await self._querier.update_crawl_job_progress(
            id=_to_uuid(job_id), progress=json.dumps(progress) if progress else None
        )

    async def cancel(
        self, job_id: str | UUID, cancelled_by: str, reason: str | None = None
    ) -> models.CrawlJob | None:
        """Cancel a job."""
        return await self._querier.cancel_crawl_job(
            id=_to_uuid(job_id), cancelled_by=cancelled_by, cancellation_reason=reason
        )


class CrawledPageRepository:
    """Repository for crawled page operations."""

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
        """Create a new crawled page record."""
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
        self, page_id: str | UUID, duplicate_of: str | UUID, similarity_score: int | None = None
    ) -> models.CrawledPage | None:
        """Mark page as duplicate."""
        return await self._querier.mark_page_as_duplicate(
            id=_to_uuid(page_id),
            duplicate_of=_to_uuid_optional(duplicate_of),
            similarity_score=similarity_score,
        )


class ContentHashRepository:
    """Repository for content hash operations."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = content_hash.AsyncQuerier(connection)

    async def upsert(
        self, content_hash_value: str, first_seen_page_id: str | UUID
    ) -> models.ContentHash | None:
        """Insert or update content hash (increments count if exists)."""
        return await self._querier.upsert_content_hash(
            content_hash=content_hash_value,
            first_seen_page_id=_to_uuid_optional(first_seen_page_id),
        )

    async def get(self, content_hash_value: str) -> models.ContentHash | None:
        """Get content hash record."""
        return await self._querier.get_content_hash(content_hash=content_hash_value)


class CrawlLogRepository:
    """Repository for crawl log operations."""

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
        log_level: str | LogLevelEnum | None = None,
        step_name: str | None = None,
        context: dict[str, Any] | None = None,
        trace_id: str | UUID | None = None,
    ) -> models.CrawlLog | None:
        """Create a new log entry."""
        log_level_enum = _ensure_log_level_enum(log_level)
        return await self._querier.create_crawl_log(
            job_id=_to_uuid(job_id),
            website_id=_to_uuid(website_id),
            step_name=step_name,
            log_level=log_level_enum,  # type: ignore[arg-type]
            message=message,
            context=json.dumps(context) if context else None,
            trace_id=_to_uuid_optional(trace_id),
        )

    async def list_by_job(
        self,
        job_id: str | UUID,
        log_level: str | LogLevelEnum | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[models.CrawlLog]:
        """List logs for a job."""
        log_level_enum = _ensure_log_level_enum(log_level)
        logs = []
        async for log in self._querier.list_logs_by_job(
            job_id=_to_uuid(job_id),
            log_level=log_level_enum,  # type: ignore[arg-type]
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
