"""Crawl log repository using sqlc-generated queries."""

import json
from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import crawl_log, models
from crawler.db.generated.models import LogLevelEnum

from .base import to_uuid, to_uuid_optional

if TYPE_CHECKING:
    from crawler.services.log_publisher import LogPublisher


class CrawlLogRepository:
    """Repository for crawl log operations using sqlc-generated queries.

    Supports optional real-time log publishing via NATS for WebSocket streaming.
    """

    def __init__(
        self,
        connection: AsyncConnection,
        log_publisher: LogPublisher | None = None,
    ):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
            log_publisher: Optional log publisher for real-time streaming via NATS.
                          If provided, logs are published to NATS after DB insert.
        """
        self.conn = connection
        self._querier = crawl_log.AsyncQuerier(connection)
        self.log_publisher = log_publisher

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

        The log is first inserted into the database (source of truth),
        then optionally published to NATS for real-time streaming.

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
        # Insert into database first (source of truth)
        log = await self._querier.create_crawl_log(
            job_id=to_uuid(job_id),
            website_id=to_uuid(website_id),
            step_name=step_name,
            log_level=log_level,
            message=message,
            context=json.dumps(context) if context else None,
            trace_id=to_uuid_optional(trace_id),
        )

        # Publish to NATS for real-time streaming (if publisher available)
        if log and self.log_publisher:
            await self.log_publisher.publish_log(log)

        return log

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

    async def stream_logs_by_job(
        self,
        job_id: str | UUID,
        after_timestamp: datetime,
        log_level: LogLevelEnum | None = None,
        limit: int = 100,
    ) -> list[models.CrawlLog]:
        """Stream logs for a job after a specific timestamp.

        This method is used for WebSocket real-time log streaming (fallback mode).
        It returns logs created after the given timestamp.

        Args:
            job_id: Job ID
            after_timestamp: Only return logs after this timestamp
            log_level: Optional log level filter
            limit: Maximum number of results

        Returns:
            List of CrawlLog models ordered by created_at ASC

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        logs = [
            log
            async for log in self._querier.stream_logs_by_job(
                job_id=to_uuid(job_id),
                after_timestamp=after_timestamp,
                log_level=log_level,  # type: ignore[arg-type]
                limit_count=limit,
            )
        ]
        return logs

    async def get_logs_after_id(
        self,
        job_id: str | UUID,
        after_log_id: int,
        log_level: LogLevelEnum | None = None,
        limit: int = 1000,
    ) -> list[models.CrawlLog]:
        """Get logs for a job after a specific log ID.

        This method is used for WebSocket reconnection with resume support.
        It returns logs with ID greater than the specified log ID.

        Args:
            job_id: Job ID
            after_log_id: Only return logs with ID greater than this
            log_level: Optional log level filter
            limit: Maximum number of results (default 1000)

        Returns:
            List of CrawlLog models ordered by id ASC

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        logs = [
            log
            async for log in self._querier.get_logs_after_id(
                job_id=to_uuid(job_id),
                after_log_id=after_log_id,
                log_level=log_level,  # type: ignore[arg-type]
                limit_count=limit,
            )
        ]
        return logs

    async def get_job_logs_filtered(
        self,
        job_id: str | UUID,
        log_level: LogLevelEnum | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        search_text: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> tuple[list[models.CrawlLog], int]:
        """Get filtered logs for a job with pagination and total count.

        Uses a window function to retrieve both logs and total count in a single query,
        reducing database round trips and improving performance.

        Args:
            job_id: Job ID
            log_level: Optional log level filter
            start_time: Optional start timestamp filter
            end_time: Optional end timestamp filter
            search_text: Optional text search in message (case-insensitive)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            Tuple of (logs list, total count) where:
            - logs: List of CrawlLog models ordered by created_at ASC
            - total: Total count of logs matching filters (for pagination)

        Note:
            SQL uses COALESCE and NULL checks, but sqlc generates non-optional types.
            The total_count is extracted from the first row via window function.
        """
        rows = [
            row
            async for row in self._querier.get_job_logs_filtered(
                job_id=to_uuid(job_id),
                log_level=log_level,  # type: ignore[arg-type]
                start_time=start_time,  # type: ignore[arg-type]
                end_time=end_time,  # type: ignore[arg-type]
                search_text=search_text,  # type: ignore[arg-type]
                limit_count=limit,
                offset_count=offset,
            )
        ]

        # Guard: No results found
        if not rows:
            return [], 0

        # Extract total count from first row (window function ensures all rows have same total)
        total_count = rows[0].total_count

        # Convert rows to CrawlLog models (excluding total_count field)
        logs = [
            models.CrawlLog(
                id=row.id,
                job_id=row.job_id,
                website_id=row.website_id,
                step_name=row.step_name,
                log_level=row.log_level,
                message=row.message,
                context=row.context,
                trace_id=row.trace_id,
                created_at=row.created_at,
            )
            for row in rows
        ]

        return logs, total_count

    async def count_job_logs_filtered(
        self,
        job_id: str | UUID,
        log_level: LogLevelEnum | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        search_text: str | None = None,
    ) -> int:
        """Count filtered logs for a job.

        .. deprecated::
            Use get_job_logs_filtered() instead, which returns both logs and count
            in a single query using a window function for better performance.

        Args:
            job_id: Job ID
            log_level: Optional log level filter
            start_time: Optional start timestamp filter
            end_time: Optional end timestamp filter
            search_text: Optional text search in message (case-insensitive)

        Returns:
            Total count of logs matching the filters

        Note:
            SQL uses COALESCE and NULL checks, but sqlc generates non-optional types.
        """
        count = await self._querier.count_job_logs_filtered(
            job_id=to_uuid(job_id),
            log_level=log_level,  # type: ignore[arg-type]
            start_time=start_time,  # type: ignore[arg-type]
            end_time=end_time,  # type: ignore[arg-type]
            search_text=search_text,  # type: ignore[arg-type]
        )
        return count or 0
