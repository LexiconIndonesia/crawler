"""Repository for retry_history table operations."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import models
from crawler.db.generated import retry_history as queries
from crawler.db.repositories.base import to_uuid


class RetryHistoryRepository:
    """Repository for retry_history table operations."""

    def __init__(self, conn: AsyncConnection):
        self.conn = conn
        self.querier = queries.AsyncQuerier(conn)

    async def create(
        self,
        job_id: str | UUID,
        attempt_number: int,
        error_category: models.ErrorCategoryEnum,
        error_message: str,
        retry_delay_seconds: int,
        stack_trace: str | None = None,
    ) -> models.RetryHistory | None:
        """Record a retry attempt.

        Args:
            job_id: ID of the job being retried
            attempt_number: The attempt number (1-indexed)
            error_category: Category of the error
            error_message: Error message (will be truncated to 1000 chars if needed)
            retry_delay_seconds: Delay before next retry in seconds
            stack_trace: Optional full stack trace

        Returns:
            Created RetryHistory record
        """
        return await self.querier.create_retry_history(
            job_id=to_uuid(job_id),
            attempt_number=attempt_number,
            error_category=error_category,
            error_message=error_message[:1000],  # Guard: ensure we don't exceed DB limit
            stack_trace=stack_trace,
            retry_delay_seconds=retry_delay_seconds,
        )

    async def get_by_job_id(self, job_id: str | UUID) -> list[models.RetryHistory]:
        """Get all retry history for a job.

        Args:
            job_id: The job ID to look up

        Returns:
            List of retry history records ordered by attempt_number
        """
        history = []
        async for record in self.querier.get_retry_history_by_job_id(job_id=to_uuid(job_id)):
            history.append(record)
        return history

    async def get_latest_attempt(self, job_id: str | UUID) -> models.RetryHistory | None:
        """Get the most recent retry attempt for a job.

        Args:
            job_id: The job ID to look up

        Returns:
            Latest retry history record, or None if no retries
        """
        return await self.querier.get_latest_retry_attempt(job_id=to_uuid(job_id))

    async def count_by_category(
        self, since: datetime
    ) -> list[queries.CountRetryAttemptsByCategoryRow]:
        """Count retry attempts grouped by error category (analytics).

        Args:
            since: Only count attempts since this timestamp

        Returns:
            List of counts per category, ordered by total_attempts DESC
        """
        counts = []
        async for count in self.querier.count_retry_attempts_by_category(attempted_at=since):
            counts.append(count)
        return counts

    async def get_failure_rate_by_category(
        self, start_time: datetime, end_time: datetime
    ) -> list[queries.GetFailureRateByCategoryRow]:
        """Get failure rate by category in a time window (analytics).

        Args:
            start_time: Start of the time window
            end_time: End of the time window

        Returns:
            List of failure counts and average delays per category
        """
        rates = []
        async for rate in self.querier.get_failure_rate_by_category(
            start_time=start_time, end_time=end_time
        ):
            rates.append(rate)
        return rates
