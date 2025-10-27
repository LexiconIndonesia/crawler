"""Database repositories using sqlc-generated queries.

Provides clean interfaces to sqlc-generated database queries.
All queries are type-safe and validated at generation time.
"""

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import content_hash
from crawler.db.generated import crawl_job
from crawler.db.generated import crawl_log
from crawler.db.generated import crawled_page
from crawler.db.generated.crawled_page import CreateCrawledPageParams
from crawler.db.generated import models
from crawler.db.generated import website


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
        status: str | None = None,
    ) -> models.Website:
        """Create a new website."""
        return await self._querier.create_website(
            name=name,
            base_url=base_url,
            config=json.dumps(config),
            created_by=created_by,
            dollar_5=status,
        )

    async def get_by_id(self, website_id: str) -> models.Website | None:
        """Get website by ID."""
        return await self._querier.get_website_by_id(id=website_id)

    async def get_by_name(self, name: str) -> models.Website | None:
        """Get website by name."""
        return await self._querier.get_website_by_name(name=name)

    async def list(
        self, status: str | None = None, limit: int = 100, offset: int = 0
    ) -> list[models.Website]:
        """List websites with pagination."""
        websites = []
        async for website_obj in self._querier.list_websites(
            status=status, limit=limit, offset=offset
        ):
            websites.append(website_obj)
        return websites

    async def count(self, status: str | None = None) -> int:
        """Count websites."""
        result = await self._querier.count_websites(status=status)
        return result if result is not None else 0

    async def update(
        self,
        website_id: str,
        name: str | None = None,
        base_url: str | None = None,
        config: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> models.Website | None:
        """Update website."""
        return await self._querier.update_website(
            id=website_id,
            name=name,
            base_url=base_url,
            config=json.dumps(config) if config else None,
            status=status,
        )

    async def delete(self, website_id: str) -> None:
        """Delete website."""
        await self._querier.delete_website(id=website_id)


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
        website_id: str,
        seed_url: str,
        job_type: str | None = None,
        embedded_config: dict[str, Any] | None = None,
        priority: int | None = None,
        scheduled_at: Any = None,
        max_retries: int | None = None,
        metadata: dict[str, Any] | None = None,
        variables: dict[str, Any] | None = None,
    ) -> models.CrawlJob:
        """Create a new crawl job."""
        return await self._querier.create_crawl_job(
            website_id=website_id,
            dollar_2=job_type,
            seed_url=seed_url,
            embedded_config=json.dumps(embedded_config) if embedded_config else None,
            dollar_5=priority,
            scheduled_at=scheduled_at,
            dollar_7=max_retries,
            metadata=json.dumps(metadata) if metadata else None,
            variables=json.dumps(variables) if variables else None,
        )

    async def get_by_id(self, job_id: str) -> models.CrawlJob | None:
        """Get crawl job by ID."""
        return await self._querier.get_crawl_job_by_id(id=job_id)

    async def get_pending(self, limit: int = 100) -> list[models.CrawlJob]:
        """Get pending jobs ordered by priority."""
        jobs = []
        async for job in self._querier.get_pending_jobs(limit=limit):
            jobs.append(job)
        return jobs

    async def update_status(
        self,
        job_id: str,
        status: str,
        started_at: Any = None,
        completed_at: Any = None,
        error_message: str | None = None,
    ) -> models.CrawlJob | None:
        """Update job status."""
        return await self._querier.update_crawl_job_status(
            id=job_id,
            dollar_2=status,
            started_at=started_at,
            completed_at=completed_at,
            error_message=error_message,
        )

    async def update_progress(
        self, job_id: str, progress: dict[str, Any]
    ) -> models.CrawlJob | None:
        """Update job progress."""
        return await self._querier.update_crawl_job_progress(
            id=job_id, progress=json.dumps(progress) if progress else None
        )

    async def cancel(
        self, job_id: str, cancelled_by: str, reason: str | None = None
    ) -> models.CrawlJob | None:
        """Cancel a job."""
        return await self._querier.cancel_crawl_job(
            id=job_id, cancelled_by=cancelled_by, cancellation_reason=reason
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
        website_id: str,
        job_id: str,
        url: str,
        url_hash: str,
        content_hash: str,
        crawled_at: Any,
        title: str | None = None,
        extracted_content: str | None = None,
        metadata: dict[str, Any] | None = None,
        gcs_html_path: str | None = None,
        gcs_documents: dict[str, Any] | None = None,
    ) -> models.CrawledPage:
        """Create a new crawled page record."""
        params = CreateCrawledPageParams(
            website_id=website_id,
            job_id=job_id,
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

    async def get_by_id(self, page_id: str) -> models.CrawledPage | None:
        """Get page by ID."""
        return await self._querier.get_crawled_page_by_id(id=page_id)

    async def get_by_url_hash(
        self, website_id: str, url_hash: str
    ) -> models.CrawledPage | None:
        """Get page by URL hash."""
        return await self._querier.get_page_by_url_hash(
            website_id=website_id, url_hash=url_hash
        )

    async def list_by_job(
        self, job_id: str, limit: int = 100, offset: int = 0
    ) -> list[models.CrawledPage]:
        """List pages for a job."""
        pages = []
        async for page in self._querier.list_pages_by_job(
            job_id=job_id, limit=limit, offset=offset
        ):
            pages.append(page)
        return pages

    async def mark_as_duplicate(
        self, page_id: str, duplicate_of: str, similarity_score: int | None = None
    ) -> models.CrawledPage | None:
        """Mark page as duplicate."""
        return await self._querier.mark_page_as_duplicate(
            id=page_id, duplicate_of=duplicate_of, similarity_score=similarity_score
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
        self, content_hash_value: str, first_seen_page_id: str
    ) -> models.ContentHash:
        """Insert or update content hash (increments count if exists)."""
        return await self._querier.upsert_content_hash(
            content_hash=content_hash_value, first_seen_page_id=first_seen_page_id
        )

    async def get(self, content_hash_value: str) -> models.ContentHash | None:
        """Get content hash record."""
        return await self._querier.get_content_hash(
            content_hash=content_hash_value
        )


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
        job_id: str,
        website_id: str,
        message: str,
        log_level: str | None = None,
        step_name: str | None = None,
        context: dict[str, Any] | None = None,
        trace_id: str | None = None,
    ) -> models.CrawlLog:
        """Create a new log entry."""
        return await self._querier.create_crawl_log(
            job_id=job_id,
            website_id=website_id,
            step_name=step_name,
            dollar_4=log_level,
            message=message,
            context=json.dumps(context) if context else None,
            trace_id=trace_id,
        )

    async def list_by_job(
        self,
        job_id: str,
        log_level: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[models.CrawlLog]:
        """List logs for a job."""
        logs = []
        async for log in self._querier.list_logs_by_job(
            job_id=job_id, log_level=log_level, limit=limit, offset=offset
        ):
            logs.append(log)
        return logs

    async def get_errors(self, job_id: str, limit: int = 100) -> list[models.CrawlLog]:
        """Get error logs for a job."""
        logs = []
        async for log in self._querier.get_error_logs(job_id=job_id, limit=limit):
            logs.append(log)
        return logs
