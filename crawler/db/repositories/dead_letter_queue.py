"""Repository for dead_letter_queue table operations."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from crawler.db.generated import dead_letter_queue as queries
from crawler.db.generated import models
from crawler.db.generated.dead_letter_queue import (
    GetDLQStatsByCategoryRow,
    GetDLQStatsRow,
)
from crawler.db.repositories.base import to_uuid

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection


class DeadLetterQueueRepository:
    """Repository for dead_letter_queue table operations.

    Error Handling Pattern:
    - Query operations (SELECT single): Return None if not found (expected case)
    - Write operations (INSERT): Raise RuntimeError on failure (unexpected)
    - Update operations: Raise RuntimeError if entry not found (unexpected)
    - Aggregate operations: Raise RuntimeError on database error (should never fail)
    """

    def __init__(self, conn: AsyncConnection):
        self.conn = conn
        self.querier = queries.AsyncQuerier(conn)

    async def add_to_dlq(
        self,
        job_id: str,
        seed_url: str,
        website_id: str | None,
        job_type: models.JobTypeEnum,
        priority: int,
        error_category: models.ErrorCategoryEnum,
        error_message: str,
        stack_trace: str | None,
        http_status: int | None,
        total_attempts: int,
        first_attempt_at: datetime,
        last_attempt_at: datetime,
    ) -> models.DeadLetterQueue:
        """Add a permanently failed job to the DLQ.

        Args:
            job_id: Job UUID
            seed_url: URL that was being crawled
            website_id: Optional website UUID
            job_type: Type of job (ONE_TIME, RECURRING)
            priority: Job priority
            error_category: Category of error
            error_message: Error message
            stack_trace: Optional stack trace
            http_status: Optional HTTP status code
            total_attempts: Total number of retry attempts
            first_attempt_at: Timestamp of first attempt
            last_attempt_at: Timestamp of last attempt

        Returns:
            Created DLQ entry
        """
        params = queries.AddToDeadLetterQueueParams(
            job_id=to_uuid(job_id),
            seed_url=seed_url,
            website_id=to_uuid(website_id) if website_id else None,
            job_type=job_type,
            priority=priority,
            error_category=error_category,
            error_message=error_message,
            stack_trace=stack_trace,
            http_status=http_status,
            total_attempts=total_attempts,
            first_attempt_at=first_attempt_at,
            last_attempt_at=last_attempt_at,
        )
        result = await self.querier.add_to_dead_letter_queue(params)
        if result is None:
            msg = f"Failed to add job {job_id} to DLQ"
            raise RuntimeError(msg)
        return result

    async def get_by_id(self, dlq_id: int) -> models.DeadLetterQueue | None:
        """Get a DLQ entry by ID.

        Args:
            dlq_id: DLQ entry ID

        Returns:
            DLQ entry if found, None otherwise
        """
        return await self.querier.get_dlq_entry_by_id(id=dlq_id)

    async def get_by_job_id(self, job_id: str) -> models.DeadLetterQueue | None:
        """Get a DLQ entry by job_id.

        Args:
            job_id: Job UUID

        Returns:
            DLQ entry if found, None otherwise
        """
        return await self.querier.get_dlq_entry_by_job_id(job_id=to_uuid(job_id))

    async def list_entries(
        self,
        error_category: models.ErrorCategoryEnum | None = None,
        website_id: str | None = None,
        unresolved_only: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[models.DeadLetterQueue]:
        """List DLQ entries with filtering and pagination.

        Args:
            error_category: Optional filter by error category
            website_id: Optional filter by website
            unresolved_only: Optional filter by resolved status
                (True=unresolved, False=resolved, None=all)
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of DLQ entries
        """
        entries = []
        async for entry in self.querier.list_dlq_entries(
            dollar_1=error_category,  # type: ignore[arg-type]
            dollar_2=to_uuid(website_id) if website_id else None,  # type: ignore[arg-type]
            dollar_3=unresolved_only,  # type: ignore[arg-type]
            limit=limit,
            offset=offset,
        ):
            entries.append(entry)
        return entries

    async def count_entries(
        self,
        error_category: models.ErrorCategoryEnum | None = None,
        website_id: str | None = None,
        unresolved_only: bool | None = None,
    ) -> int:
        """Count DLQ entries with filtering.

        Args:
            error_category: Optional filter by error category
            website_id: Optional filter by website
            unresolved_only: Optional filter by resolved status

        Returns:
            Count of matching entries
        """
        result = await self.querier.count_dlq_entries(
            dollar_1=error_category,  # type: ignore[arg-type]
            dollar_2=to_uuid(website_id) if website_id else None,  # type: ignore[arg-type]
            dollar_3=unresolved_only,  # type: ignore[arg-type]
        )
        return result or 0

    async def mark_retry_attempted(self, dlq_id: int, success: bool) -> models.DeadLetterQueue:
        """Mark that a DLQ entry was manually retried.

        Args:
            dlq_id: DLQ entry ID
            success: Whether the retry was successful

        Returns:
            Updated DLQ entry

        Raises:
            RuntimeError: If DLQ entry not found
        """
        result = await self.querier.mark_dlq_retry_attempted(id=dlq_id, retry_success=success)
        if result is None:
            msg = f"DLQ entry {dlq_id} not found"
            raise RuntimeError(msg)
        return result

    async def mark_resolved(
        self, dlq_id: int, resolution_notes: str | None = None
    ) -> models.DeadLetterQueue:
        """Mark a DLQ entry as resolved.

        Args:
            dlq_id: DLQ entry ID
            resolution_notes: Optional notes about the resolution

        Returns:
            Updated DLQ entry

        Raises:
            RuntimeError: If DLQ entry not found
        """
        result = await self.querier.mark_dlq_resolved(id=dlq_id, resolution_notes=resolution_notes)
        if result is None:
            msg = f"DLQ entry {dlq_id} not found"
            raise RuntimeError(msg)
        return result

    async def get_stats(self) -> GetDLQStatsRow:
        """Get overall DLQ statistics.

        Returns:
            Statistics including total, unresolved, retry attempts, successes
        """
        result = await self.querier.get_dlq_stats()
        if result is None:
            msg = "Failed to get DLQ stats"
            raise RuntimeError(msg)
        return result

    async def get_stats_by_category(self) -> list[GetDLQStatsByCategoryRow]:
        """Get DLQ statistics grouped by error category.

        Returns:
            List of category statistics
        """
        stats = []
        async for stat in self.querier.get_dlq_stats_by_category():
            stats.append(stat)
        return stats

    async def get_entries_for_website(
        self, website_id: str, limit: int = 100, offset: int = 0
    ) -> list[models.DeadLetterQueue]:
        """Get all DLQ entries for a specific website.

        Args:
            website_id: Website UUID
            limit: Maximum number of entries to return
            offset: Number of entries to skip

        Returns:
            List of DLQ entries for the website
        """
        entries = []
        async for entry in self.querier.get_dlq_entries_for_website(
            website_id=to_uuid(website_id), limit=limit, offset=offset
        ):
            entries.append(entry)
        return entries

    async def delete_entry(self, dlq_id: int) -> None:
        """Delete a DLQ entry (hard delete).

        Args:
            dlq_id: DLQ entry ID

        Raises:
            RuntimeError: If DLQ entry not found
        """
        # Check if entry exists before deleting
        entry = await self.get_by_id(dlq_id)
        if entry is None:
            msg = f"DLQ entry {dlq_id} not found"
            raise RuntimeError(msg)

        await self.querier.delete_dlq_entry(id=dlq_id)

    async def get_oldest_unresolved(self, limit: int = 10) -> list[models.DeadLetterQueue]:
        """Get oldest unresolved DLQ entries (useful for alerting).

        Args:
            limit: Maximum number of entries to return

        Returns:
            List of oldest unresolved entries
        """
        entries = []
        async for entry in self.querier.get_oldest_unresolved_dlq_entries(limit=limit):
            entries.append(entry)
        return entries

    async def bulk_mark_resolved(
        self, dlq_ids: list[int], resolution_notes: str | None = None
    ) -> int:
        """Mark multiple DLQ entries as resolved.

        Args:
            dlq_ids: List of DLQ entry IDs
            resolution_notes: Optional notes about the resolution

        Returns:
            Number of entries marked as resolved

        Raises:
            RuntimeError: If bulk update fails
        """
        if not dlq_ids:
            return 0

        try:
            await self.querier.bulk_mark_dlq_resolved(
                dollar_1=dlq_ids, resolution_notes=resolution_notes
            )
            # Return count of IDs provided (assuming all succeeded)
            return len(dlq_ids)
        except Exception as e:
            msg = f"Failed to bulk mark {len(dlq_ids)} DLQ entries as resolved"
            raise RuntimeError(msg) from e
