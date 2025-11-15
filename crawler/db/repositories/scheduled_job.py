"""Scheduled job repository using sqlc-generated queries."""

import json
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import models, scheduled_job

from .base import to_uuid


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
        timezone: str,
        is_active: bool | None = None,
        job_config: dict[str, Any] | None = None,
    ) -> models.ScheduledJob | None:
        """Create a new scheduled job.

        Args:
            website_id: Website ID
            cron_schedule: Cron expression for schedule
            next_run_time: Next scheduled execution time (in UTC)
            timezone: IANA timezone name for schedule calculations
            is_active: Optional active flag (uses true default if None)
            job_config: Optional job config dict (will be serialized to JSON)

        Returns:
            Created ScheduledJob model or None
        """
        return await self._querier.create_scheduled_job(
            website_id=to_uuid(website_id),
            cron_schedule=cron_schedule,
            next_run_time=next_run_time,
            is_active=is_active,
            job_config=json.dumps(job_config) if job_config else None,
            timezone=timezone,
        )

    async def get_by_id(self, job_id: str | UUID) -> models.ScheduledJob | None:
        """Get scheduled job by ID with deserialized job_config."""
        job = await self._querier.get_scheduled_job_by_id(id=to_uuid(job_id))
        return self._deserialize_job_config(job)

    async def get_by_website_id(self, website_id: str | UUID) -> list[models.ScheduledJob]:
        """Get all scheduled jobs for a website with deserialized job_config."""
        jobs = []
        async for job in self._querier.get_scheduled_jobs_by_website_id(
            website_id=to_uuid(website_id)
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
        timezone: str | None = None,
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
            timezone: New timezone (optional, uses existing if None)

        Returns:
            Updated ScheduledJob model or None

        Note:
            SQL uses COALESCE for all parameters, but sqlc generates non-optional types.
        """
        # sqlc generates non-optional types but SQL supports COALESCE (optional updates)
        return await self._querier.update_scheduled_job(  # type: ignore[arg-type]
            id=to_uuid(job_id),
            cron_schedule=cron_schedule,  # type: ignore[arg-type]
            next_run_time=next_run_time,  # type: ignore[arg-type]
            last_run_time=last_run_time,
            is_active=is_active,  # type: ignore[arg-type]
            job_config=json.dumps(job_config) if job_config else None,
            timezone=timezone,  # type: ignore[arg-type]
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
            id=to_uuid(job_id), next_run_time=next_run_time, last_run_time=last_run_time
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
            id=to_uuid(job_id), is_active=is_active
        )

    async def delete(self, job_id: str | UUID) -> None:
        """Delete scheduled job."""
        await self._querier.delete_scheduled_job(id=to_uuid(job_id))

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
            website_id=to_uuid(website_id) if website_id else None,  # type: ignore[arg-type]
            is_active=is_active,  # type: ignore[arg-type]
        )
        return result if result is not None else 0
