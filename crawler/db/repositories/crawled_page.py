"""Crawled page repository using sqlc-generated queries."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import crawled_page, models
from crawler.db.generated.crawled_page import CreateCrawledPageParams

from .base import to_uuid, to_uuid_optional


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
            website_id=to_uuid(website_id),
            job_id=to_uuid(job_id),
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
        return await self._querier.get_crawled_page_by_id(id=to_uuid(page_id))

    async def get_by_url_hash(
        self, website_id: str | UUID, url_hash: str
    ) -> models.CrawledPage | None:
        """Get page by URL hash."""
        return await self._querier.get_page_by_url_hash(
            website_id=to_uuid(website_id), url_hash=url_hash
        )

    async def get_by_content_hash(self, content_hash: str) -> models.CrawledPage | None:
        """Get first page with matching content hash (for duplicate detection).

        Args:
            content_hash: SHA256 hash of page content

        Returns:
            First CrawledPage with matching content_hash, or None if not found
        """
        return await self._querier.get_page_by_content_hash(content_hash=content_hash)

    async def list_by_job(
        self, job_id: str | UUID, limit: int = 100, offset: int = 0
    ) -> list[models.CrawledPage]:
        """List pages for a job."""
        pages = []
        async for page in self._querier.list_pages_by_job(
            job_id=to_uuid(job_id), limit_count=limit, offset_count=offset
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
            id=to_uuid(page_id),
            duplicate_of=to_uuid_optional(duplicate_of),
            similarity_score=similarity_score,
        )
