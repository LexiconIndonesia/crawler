"""Scheduled job service with business logic."""

from datetime import datetime
from typing import Any
from uuid import UUID

from crawler.api.generated import (
    ListScheduledJobsResponse,
    ScheduledJobResponse,
    ScheduledJobSummary,
    UpdateScheduledJobRequest,
)
from crawler.api.validators import validate_and_calculate_next_run
from crawler.core.logging import get_logger
from crawler.db.repositories import ScheduledJobRepository, WebsiteRepository

logger = get_logger(__name__)


class ScheduledJobService:
    """Service for scheduled job operations with business logic."""

    def __init__(
        self,
        scheduled_job_repo: ScheduledJobRepository,
        website_repo: WebsiteRepository,
    ):
        """Initialize service with dependencies.

        Args:
            scheduled_job_repo: Scheduled job repository for database access
            website_repo: Website repository for validation and website name lookup
        """
        self.scheduled_job_repo = scheduled_job_repo
        self.website_repo = website_repo

    async def list_scheduled_jobs(
        self,
        website_id: str | UUID | None = None,
        is_active: bool | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> ListScheduledJobsResponse:
        """List scheduled jobs with filtering and pagination.

        Args:
            website_id: Optional website ID filter
            is_active: Optional active status filter
            limit: Maximum number of results (default: 20, max: 100)
            offset: Number of results to skip (default: 0)

        Returns:
            Paginated list of scheduled jobs with total count

        Raises:
            ValueError: If website_id is invalid or website not found
            RuntimeError: If database operation fails
        """
        logger.info(
            "list_scheduled_jobs",
            website_id=str(website_id) if website_id else None,
            is_active=is_active,
            limit=limit,
            offset=offset,
        )

        # Guard: validate website exists if filter is provided
        if website_id:
            website = await self.website_repo.get_by_id(str(website_id))
            if not website:
                logger.warning("website_not_found_for_filter", website_id=str(website_id))
                raise ValueError(f"Website with ID '{website_id}' not found")

        # Get scheduled jobs based on filters
        if website_id and is_active is not None:
            # Filter by both website_id and is_active
            # Get all jobs for website and filter by status
            all_jobs = await self.scheduled_job_repo.get_by_website_id(str(website_id))
            filtered_jobs = [job for job in all_jobs if job.is_active == is_active]
            # Apply pagination manually
            jobs = filtered_jobs[offset : offset + limit]
            total = len(filtered_jobs)
        elif website_id:
            # Filter by website_id only
            all_jobs = await self.scheduled_job_repo.get_by_website_id(str(website_id))
            jobs = all_jobs[offset : offset + limit]
            total = len(all_jobs)
        elif is_active is not None:
            # Filter by is_active only - use list_by_status for both active and inactive
            jobs = await self.scheduled_job_repo.list_by_status(
                is_active=is_active, limit=limit, offset=offset
            )
            total = await self.scheduled_job_repo.count(is_active=is_active)
        else:
            # No filters - list all active jobs (default behavior)
            jobs = await self.scheduled_job_repo.list_active(limit=limit, offset=offset)
            total = await self.scheduled_job_repo.count()

        # Build summary list with website names
        # Cache websites by ID to avoid N+1 queries (many jobs may share few websites)
        website_cache: dict[str, str] = {}  # website_id -> website_name
        summaries = []
        for job in jobs:
            # Get website name from cache or fetch once and cache it
            website_id_str = str(job.website_id)
            if website_id_str not in website_cache:
                website = await self.website_repo.get_by_id(website_id_str)
                website_cache[website_id_str] = website.name if website else "Unknown"

            website_name = website_cache[website_id_str]

            summaries.append(
                ScheduledJobSummary(
                    id=job.id,
                    website_id=job.website_id,
                    website_name=website_name,
                    cron_schedule=job.cron_schedule,
                    timezone=job.timezone,
                    is_active=job.is_active,
                    next_run_time=job.next_run_time,
                    last_run_time=job.last_run_time,
                    created_at=job.created_at,
                    updated_at=job.updated_at,
                )
            )

        logger.info("scheduled_jobs_listed", count=len(summaries), total=total)

        return ListScheduledJobsResponse(
            scheduled_jobs=summaries,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def get_scheduled_job(self, job_id: str | UUID) -> ScheduledJobResponse:
        """Get scheduled job by ID with full details.

        Args:
            job_id: Scheduled job ID

        Returns:
            Scheduled job response with full details including job_config

        Raises:
            ValueError: If scheduled job not found
            RuntimeError: If database operation fails
        """
        logger.info("get_scheduled_job", job_id=str(job_id))

        # Get scheduled job
        job = await self.scheduled_job_repo.get_by_id(str(job_id))
        if not job:
            logger.warning("scheduled_job_not_found", job_id=str(job_id))
            raise ValueError(f"Scheduled job with ID '{job_id}' not found")

        # Get website name
        website = await self.website_repo.get_by_id(str(job.website_id))
        if not website:
            logger.warning(
                "website_not_found_for_scheduled_job",
                job_id=str(job_id),
                website_id=str(job.website_id),
            )
            raise RuntimeError(f"Website with ID '{job.website_id}' not found for scheduled job")

        logger.info("scheduled_job_retrieved", job_id=str(job_id))

        return ScheduledJobResponse(
            id=job.id,
            website_id=job.website_id,
            website_name=website.name,
            cron_schedule=job.cron_schedule,
            timezone=job.timezone,
            next_run_time=job.next_run_time,
            last_run_time=job.last_run_time,
            is_active=job.is_active,
            job_config=job.job_config,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def update_scheduled_job(
        self, job_id: str | UUID, request: UpdateScheduledJobRequest
    ) -> ScheduledJobResponse:
        """Update scheduled job configuration.

        Args:
            job_id: Scheduled job ID
            request: Update request with optional fields

        Returns:
            Updated scheduled job response

        Raises:
            ValueError: If scheduled job not found or validation fails
            RuntimeError: If update operation fails
        """
        logger.info("update_scheduled_job", job_id=str(job_id))

        # Guard: validate scheduled job exists
        job = await self.scheduled_job_repo.get_by_id(str(job_id))
        if not job:
            logger.warning("scheduled_job_not_found_for_update", job_id=str(job_id))
            raise ValueError(f"Scheduled job with ID '{job_id}' not found")

        # Check if there are any changes
        has_changes = False

        # Track individual update parameters
        new_cron_schedule: str | None = None
        new_next_run_time: datetime | None = None
        new_timezone: str | None = None
        new_is_active: bool | None = None
        new_job_config: dict[str, Any] | None = None

        # Update cron schedule if provided
        if request.cron_schedule is not None:
            # Use provided timezone or existing job timezone
            effective_timezone = request.timezone if request.timezone is not None else job.timezone

            # Validate cron expression and calculate next run time
            is_valid, result = validate_and_calculate_next_run(
                request.cron_schedule,
                timezone=effective_timezone,
            )
            if not is_valid:
                logger.warning(
                    "invalid_cron_in_update",
                    job_id=str(job_id),
                    cron=request.cron_schedule,
                    timezone=effective_timezone,
                    error=result,
                )
                raise ValueError(f"Invalid cron expression: {result}")

            # Type guard: result must be datetime if is_valid is True
            if not isinstance(result, datetime):
                logger.error(
                    "unexpected_validation_result_type",
                    job_id=str(job_id),
                    result_type=type(result).__name__,
                )
                raise RuntimeError("Unexpected validation result type")

            new_next_run_time = result
            new_cron_schedule = request.cron_schedule
            has_changes = True

            logger.info(
                "cron_schedule_updated",
                job_id=str(job_id),
                old_cron=job.cron_schedule,
                new_cron=request.cron_schedule,
                next_run_time=new_next_run_time.isoformat(),
            )

        # Update timezone if provided (independently of cron_schedule)
        if request.timezone is not None and request.cron_schedule is None:
            # Timezone changed but cron didn't - recalculate next_run_time with new timezone
            is_valid, result = validate_and_calculate_next_run(
                job.cron_schedule,
                timezone=request.timezone,
            )
            if not is_valid:
                logger.warning(
                    "invalid_timezone_in_update",
                    job_id=str(job_id),
                    timezone=request.timezone,
                    error=result,
                )
                raise ValueError(f"Invalid timezone: {result}")

            if not isinstance(result, datetime):
                raise RuntimeError("Unexpected validation result type")

            new_next_run_time = result
            new_timezone = request.timezone
            has_changes = True

            logger.info(
                "timezone_updated",
                job_id=str(job_id),
                old_timezone=job.timezone,
                new_timezone=request.timezone,
                next_run_time=new_next_run_time.isoformat(),
            )
        elif request.timezone is not None:
            # Timezone provided along with cron_schedule - already handled above
            new_timezone = request.timezone

        # Update is_active if provided
        if request.is_active is not None and request.is_active != job.is_active:
            new_is_active = request.is_active
            has_changes = True
            logger.info(
                "is_active_updated",
                job_id=str(job_id),
                old_is_active=job.is_active,
                new_is_active=request.is_active,
            )

        # Update job_config if provided
        if request.job_config is not None:
            new_job_config = request.job_config
            has_changes = True
            logger.info("job_config_updated", job_id=str(job_id))

        # Guard: no changes detected
        if not has_changes:
            logger.info("no_changes_in_scheduled_job_update", job_id=str(job_id))
            raise ValueError("No changes detected in the update request")

        # Update scheduled job
        updated_job = await self.scheduled_job_repo.update(
            job_id=str(job_id),
            cron_schedule=new_cron_schedule,
            next_run_time=new_next_run_time,
            is_active=new_is_active,
            job_config=new_job_config,
            timezone=new_timezone,
        )

        if not updated_job:
            logger.error("scheduled_job_update_failed", job_id=str(job_id))
            raise RuntimeError("Failed to update scheduled job")

        # Get website name for response
        website = await self.website_repo.get_by_id(str(updated_job.website_id))
        if not website:
            logger.warning(
                "website_not_found_after_update",
                job_id=str(job_id),
                website_id=str(updated_job.website_id),
            )
            raise RuntimeError(f"Website with ID '{updated_job.website_id}' not found after update")

        logger.info("scheduled_job_updated", job_id=str(job_id))

        return ScheduledJobResponse(
            id=updated_job.id,
            website_id=updated_job.website_id,
            website_name=website.name,
            cron_schedule=updated_job.cron_schedule,
            timezone=updated_job.timezone,
            next_run_time=updated_job.next_run_time,
            last_run_time=updated_job.last_run_time,
            is_active=updated_job.is_active,
            job_config=updated_job.job_config,
            created_at=updated_job.created_at,
            updated_at=updated_job.updated_at,
        )

    async def delete_scheduled_job(self, job_id: str | UUID) -> dict:
        """Delete scheduled job.

        Args:
            job_id: Scheduled job ID

        Returns:
            Deletion confirmation message

        Raises:
            ValueError: If scheduled job not found
            RuntimeError: If deletion operation fails
        """
        logger.info("delete_scheduled_job", job_id=str(job_id))

        # Guard: validate scheduled job exists
        job = await self.scheduled_job_repo.get_by_id(str(job_id))
        if not job:
            logger.warning("scheduled_job_not_found_for_delete", job_id=str(job_id))
            raise ValueError(f"Scheduled job with ID '{job_id}' not found")

        # Delete scheduled job
        await self.scheduled_job_repo.delete(str(job_id))

        logger.info(
            "scheduled_job_deleted",
            job_id=str(job_id),
            website_id=str(job.website_id),
        )

        return {
            "message": f"Scheduled job '{job_id}' deleted successfully",
            "id": str(job_id),
            "website_id": str(job.website_id),
        }
