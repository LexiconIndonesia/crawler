"""Crawl log repository using sqlc-generated queries."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import crawl_log, models
from crawler.db.generated.models import LogLevelEnum

from .base import to_uuid, to_uuid_optional


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
        log_level: LogLevelEnum = LogLevelEnum.INFO,
        step_name: str | None = None,
        context: dict[str, Any] | None = None,
        trace_id: str | UUID | None = None,
    ) -> models.CrawlLog | None:
        """Create a new log entry.

        Args:
            job_id: Job ID
            website_id: Website ID
            message: Log message
            log_level: Log level enum (defaults to INFO)
            step_name: Optional step name
            context: Optional context dict (will be serialized to JSON)
            trace_id: Optional trace ID for distributed tracing

        Returns:
            Created CrawlLog model or None
        """
        return await self._querier.create_crawl_log(
            job_id=to_uuid(job_id),
            website_id=to_uuid(website_id),
            step_name=step_name,
            log_level=log_level.value,
            message=message,
            context=json.dumps(context) if context else None,
            trace_id=to_uuid_optional(trace_id),
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
            job_id=to_uuid(job_id),
            log_level=log_level,  # type: ignore[arg-type]
            limit_count=limit,
            offset_count=offset,
        ):
            logs.append(log)
        return logs

    async def get_errors(self, job_id: str | UUID, limit: int = 100) -> list[models.CrawlLog]:
        """Get error logs for a job."""
        logs = []
        async for log in self._querier.get_error_logs(job_id=to_uuid(job_id), limit_count=limit):
            logs.append(log)
        return logs
