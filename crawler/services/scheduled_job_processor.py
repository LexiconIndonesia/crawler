"""Scheduled job processor for creating crawl jobs from scheduled jobs.

This module provides a background service that:
1. Polls the database for scheduled jobs that are due
2. Creates crawl jobs for each due scheduled job
3. Publishes the jobs to NATS queue for workers to pick up
4. Updates the next_run_time for recurring jobs
5. Handles graceful shutdown and restart
6. Handles missed schedules after downtime (catch-up within 1 hour)
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from crawler.core.logging import get_logger
from crawler.core.metrics import scheduled_jobs_processed_total, scheduled_jobs_skipped_total
from crawler.db.generated.models import JobTypeEnum, StatusEnum
from crawler.utils.cron import calculate_next_run
from crawler.utils.dst import get_dst_transition_type

if TYPE_CHECKING:
    from crawler.db.repositories.crawl_job import CrawlJobRepository
    from crawler.db.repositories.scheduled_job import ScheduledJobRepository
    from crawler.db.repositories.website import WebsiteRepository
    from crawler.services.nats_queue import NATSQueueService

logger = get_logger(__name__)

# Global task reference for lifecycle management
_processor_task: asyncio.Task | None = None

# Maximum delay for catch-up (1 hour)
MAX_CATCHUP_DELAY = timedelta(hours=1)

# Default priority for scheduled jobs created by the processor
SCHEDULED_JOB_PRIORITY = 5


async def _prepare_scheduled_job(
    scheduled_job: Any,
    scheduled_job_repo: ScheduledJobRepository,
    now: datetime,
) -> tuple[str, bool]:
    """Prepare a scheduled job by handling timezone backfill and orphaned state.

    This helper extracts common logic for:
    - Deriving job timezone with UTC fallback
    - Backfilling missing timezone on legacy jobs
    - Handling orphaned jobs with next_run_time=None

    Args:
        scheduled_job: Scheduled job to prepare
        scheduled_job_repo: Repository for scheduled job operations
        now: Current timestamp for calculating next run time

    Returns:
        Tuple of (job_timezone, should_continue) where:
        - job_timezone: The timezone to use (fallback to "UTC" if missing)
        - should_continue: False if job is invalid and should be skipped, True otherwise

    Raises:
        None - errors are logged and handled via return value
    """
    # Extract timezone with backward compatibility fallback
    job_timezone = (
        scheduled_job.timezone
        if hasattr(scheduled_job, "timezone") and scheduled_job.timezone
        else "UTC"
    )

    # Backfill: If timezone is missing or null, update it to UTC for future consistency
    # This handles legacy jobs created before timezone column was added
    if not hasattr(scheduled_job, "timezone") or not scheduled_job.timezone:
        logger.info(
            "backfilling_timezone_on_legacy_job",
            scheduled_job_id=str(scheduled_job.id),
            timezone="UTC",
            reason="Job has no timezone - backfilling with UTC default",
        )
        try:
            await scheduled_job_repo.update(
                job_id=str(scheduled_job.id),
                timezone="UTC",
            )
        except Exception as e:
            logger.warning(
                "timezone_backfill_failed",
                scheduled_job_id=str(scheduled_job.id),
                error=str(e),
                reason="Could not backfill timezone - will use fallback",
            )

    # Guard: orphaned job with no next_run_time
    # This can happen if job was manually updated or migration failed
    # Calculate new next_run_time and update job (no catch-up execution)
    if scheduled_job.next_run_time is None:
        logger.warning(
            "orphaned_job_no_next_run_time",
            scheduled_job_id=str(scheduled_job.id),
            cron_schedule=scheduled_job.cron_schedule,
            timezone=job_timezone,
            reason="Job has no next_run_time - calculating new schedule",
        )
        try:
            new_next_run_time = calculate_next_run(
                scheduled_job.cron_schedule, now, timezone=job_timezone
            )
            await scheduled_job_repo.update_next_run(
                job_id=str(scheduled_job.id),
                next_run_time=new_next_run_time,
                last_run_time=None,  # No execution, so don't set last_run_time
            )
            logger.info(
                "orphaned_job_rescheduled",
                scheduled_job_id=str(scheduled_job.id),
                next_run_time=new_next_run_time.isoformat(),
                timezone=job_timezone,
            )
        except ValueError as e:
            logger.error(
                "orphaned_job_invalid_cron",
                scheduled_job_id=str(scheduled_job.id),
                cron_schedule=scheduled_job.cron_schedule,
                error=str(e),
                reason="Cannot calculate next_run_time - deactivating job",
            )
            await scheduled_job_repo.toggle_status(job_id=str(scheduled_job.id), is_active=False)
            return (job_timezone, False)  # Signal to skip this job

    return (job_timezone, True)  # Job is valid, continue processing


async def _create_and_publish_crawl_job(
    crawl_job_repo: CrawlJobRepository,
    nats_queue: NATSQueueService,
    website_id: str,
    seed_url: str,
    job_config: dict[str, Any] | None,
    scheduled_job_id: str,
    cron_schedule: str,
    now: datetime,
    is_catchup: bool = False,
    missed_time: datetime | None = None,
) -> str | None:
    """Create and publish a crawl job. Returns crawl_job_id on success, None on failure.

    Args:
        crawl_job_repo: Repository for crawl job operations
        nats_queue: NATS queue service for job publishing
        website_id: Website ID for the crawl job
        seed_url: Seed URL to start crawling from
        job_config: Job configuration variables
        scheduled_job_id: ID of the scheduled job that triggered this crawl
        cron_schedule: Cron schedule expression
        now: Current timestamp
        is_catchup: Whether this is a catch-up job for a missed schedule
        missed_time: The original scheduled time that was missed (for catch-up jobs)

    Returns:
        Crawl job ID on success, None on failure
    """
    # Build metadata (mix of str and bool values)
    metadata: dict[str, str | bool] = {
        "scheduled_job_id": scheduled_job_id,
        "cron_schedule": cron_schedule,
    }
    if is_catchup:
        metadata["catchup"] = True  # Store as boolean for type safety
        if missed_time:
            metadata["missed_time"] = missed_time.isoformat()

    # Create crawl job
    crawl_job = await crawl_job_repo.create_template_based_job(
        website_id=website_id,
        seed_url=seed_url,
        variables=job_config or {},
        job_type=JobTypeEnum.SCHEDULED,
        priority=SCHEDULED_JOB_PRIORITY,  # Normal scheduled job priority
        scheduled_at=now,
        max_retries=3,
        metadata=metadata,
    )

    # Guard: job creation failed
    if not crawl_job:
        logger.error(
            "job_creation_failed",
            scheduled_job_id=scheduled_job_id,
            reason="create_template_based_job returned None",
        )
        return None

    # Publish job to NATS queue
    job_data = {
        "website_id": str(crawl_job.website_id) if crawl_job.website_id else None,
        "seed_url": crawl_job.seed_url,
        "job_type": crawl_job.job_type.value,
        "priority": crawl_job.priority,
    }
    published = await nats_queue.publish_job(str(crawl_job.id), job_data)

    # Guard: publish failed
    # Mark as CANCELLED (not FAILED) since job was never executed - just couldn't be queued
    if not published:
        logger.error(
            "job_publish_failed",
            crawl_job_id=str(crawl_job.id),
            scheduled_job_id=scheduled_job_id,
            reason="Could not publish to NATS queue - marking as cancelled",
        )
        await crawl_job_repo.update_status(job_id=str(crawl_job.id), status=StatusEnum.CANCELLED)
        return None

    return str(crawl_job.id)


async def handle_missed_schedules(
    scheduled_job_repo: ScheduledJobRepository,
    crawl_job_repo: CrawlJobRepository,
    website_repo: WebsiteRepository,
    nats_queue: NATSQueueService,
    batch_size: int = 100,
) -> tuple[int, int]:
    """Handle missed schedules after scheduler restart/downtime.

    This function detects schedules that were missed during downtime and:
    - Catches up (executes immediately) if missed by < 1 hour
    - Skips (just reschedules) if missed by > 1 hour

    Args:
        scheduled_job_repo: Repository for scheduled job operations
        crawl_job_repo: Repository for crawl job operations
        website_repo: Repository for website operations
        nats_queue: NATS queue service for job publishing
        batch_size: Maximum number of jobs to process per batch

    Returns:
        Tuple of (caught_up_count, skipped_count)

    Design:
    - Missed schedule = next_run_time is in the past (< now) and is_active=true
    - Catch-up threshold = now - 1 hour
    - Jobs missed by < 1 hour: execute immediately + reschedule
    - Jobs missed by > 1 hour: skip execution, just reschedule
    - All rescheduling uses calculate_next_run(cron, now) for consistency
    """
    now = datetime.now(UTC)
    catchup_threshold = now - MAX_CATCHUP_DELAY
    caught_up = 0
    skipped = 0
    total_processed = 0

    logger.info(
        "checking_missed_schedules",
        now=now.isoformat(),
        catchup_threshold=catchup_threshold.isoformat(),
        max_catchup_hours=MAX_CATCHUP_DELAY.total_seconds() / 3600,
    )

    # Loop to drain all overdue jobs, not just one batch
    # Critical: without this loop, jobs beyond batch_size would bypass the 1-hour skip rule
    # and be executed as "normal" jobs on the next cycle
    while True:
        try:
            # Get next batch of active jobs with next_run_time in the past
            # Use cutoff_time = now to get all overdue jobs
            missed_jobs = await scheduled_job_repo.get_due_jobs(cutoff_time=now, limit=batch_size)
        except Exception as e:
            logger.error(
                "missed_schedule_query_failed",
                error=str(e),
                reason="Failed to query missed schedules from database",
            )
            break  # Exit loop on query error

        if not missed_jobs:
            # No more overdue jobs - we've drained the backlog
            break

        batch_count = len(missed_jobs)
        logger.info(
            "processing_missed_schedules_batch",
            batch_size=batch_count,
            total_processed_so_far=total_processed,
        )

        for job in missed_jobs:
            try:
                # Guard: website not found or deleted
                website = await website_repo.get_by_id(str(job.website_id))
                if not website or website.deleted_at is not None:
                    logger.warning(
                        "website_not_found_for_missed_job",
                        scheduled_job_id=str(job.id),
                        website_id=str(job.website_id),
                        reason="Website deleted or not found - deactivating scheduled job",
                    )
                    await scheduled_job_repo.toggle_status(job_id=str(job.id), is_active=False)
                    continue

                # Prepare job: handle timezone backfill and orphaned state
                job_timezone, should_continue = await _prepare_scheduled_job(
                    job, scheduled_job_repo, now
                )
                if not should_continue:
                    continue

                delay = now - job.next_run_time
                should_catchup = delay < MAX_CATCHUP_DELAY

                try:
                    next_run_time = calculate_next_run(
                        job.cron_schedule, now, timezone=job_timezone
                    )

                    # Check for DST transition in the job's timezone
                    dst_transition = get_dst_transition_type(next_run_time, job_timezone)
                    if dst_transition:
                        logger.info(
                            "dst_transition_on_catchup",
                            scheduled_job_id=str(job.id),
                            next_run_time=next_run_time.isoformat(),
                            timezone=job_timezone,
                            transition_type=dst_transition,
                            note="DST transition detected - next run time adjusted automatically",
                        )
                except ValueError as e:
                    logger.error(
                        "cron_calculation_failed_for_missed_job",
                        scheduled_job_id=str(job.id),
                        cron_schedule=job.cron_schedule,
                        error=str(e),
                        reason="Invalid cron - deactivating job",
                    )
                    await scheduled_job_repo.toggle_status(job_id=str(job.id), is_active=False)
                    continue

                if should_catchup:
                    # Catch up: execute now + reschedule
                    logger.info(
                        "catching_up_missed_schedule",
                        scheduled_job_id=str(job.id),
                        website_id=str(job.website_id),
                        website_name=website.name,
                        missed_time=job.next_run_time.isoformat(),
                        delay_minutes=delay.total_seconds() / 60,
                        next_run_time=next_run_time.isoformat(),
                    )

                    # Create and publish crawl job (same as regular processing)
                    crawl_job_id = await _create_and_publish_crawl_job(
                        crawl_job_repo=crawl_job_repo,
                        nats_queue=nats_queue,
                        website_id=str(job.website_id),
                        seed_url=website.base_url,
                        job_config=job.job_config,
                        scheduled_job_id=str(job.id),
                        cron_schedule=job.cron_schedule,
                        now=now,
                        is_catchup=True,
                        missed_time=job.next_run_time,
                    )

                    # Guard: job creation or publishing failed
                    if not crawl_job_id:
                        continue

                    caught_up += 1
                    scheduled_jobs_processed_total.labels(processing_type="catchup").inc()

                else:
                    # Skip: just reschedule without executing
                    delay_hours = delay.total_seconds() / 3600
                    logger.warning(
                        "skipping_missed_schedule",
                        scheduled_job_id=str(job.id),
                        website_id=str(job.website_id),
                        website_name=website.name,
                        missed_time=job.next_run_time.isoformat(),
                        delay_hours=delay_hours,
                        next_run_time=next_run_time.isoformat(),
                        reason=f"Missed by {delay_hours:.1f} hours (> 1 hour threshold)",
                    )
                    skipped += 1
                    scheduled_jobs_skipped_total.labels(reason="missed_threshold").inc()

                # Update next_run_time for both caught-up and skipped jobs
                await scheduled_job_repo.update_next_run(
                    job_id=str(job.id),
                    next_run_time=next_run_time,
                    last_run_time=now if should_catchup else job.last_run_time,
                )

            except Exception as e:
                logger.error(
                    "missed_schedule_processing_error",
                    scheduled_job_id=str(job.id),
                    error=str(e),
                    exc_info=True,
                    reason="Unexpected error processing missed schedule - continuing",
                )
                continue

        # Track total processed in this batch
        total_processed += batch_count

        # If we got a full batch, there might be more overdue jobs - continue looping
        # If we got fewer than batch_size, we've drained the backlog - exit loop
        if batch_count < batch_size:
            logger.info(
                "missed_schedule_backlog_drained",
                total_processed=total_processed,
                caught_up=caught_up,
                skipped=skipped,
            )
            break

    # Final summary after draining all overdue jobs
    logger.info(
        "missed_schedule_handling_complete",
        total_processed=total_processed,
        caught_up=caught_up,
        skipped=skipped,
    )

    return (caught_up, skipped)


async def process_scheduled_jobs(
    scheduled_job_repo: ScheduledJobRepository,
    crawl_job_repo: CrawlJobRepository,
    website_repo: WebsiteRepository,
    nats_queue: NATSQueueService,
    batch_size: int = 100,
) -> int:
    """Process all due scheduled jobs.

    Args:
        scheduled_job_repo: Repository for scheduled job operations
        crawl_job_repo: Repository for crawl job operations
        website_repo: Repository for website operations
        nats_queue: NATS queue service for job publishing
        batch_size: Maximum number of jobs to process per batch

    Returns:
        Number of jobs successfully processed

    This function:
    1. Queries for jobs due now (next_run_time <= now)
    2. For each due job:
       - Fetches website to get base_url (seed_url)
       - Creates a crawl job (template-based, using website config)
       - Publishes to NATS queue
       - Calculates next run time from cron expression
       - Updates scheduled job's next_run_time
    3. Handles errors gracefully (logs and continues)
    """
    now = datetime.now(UTC)
    processed_count = 0

    # Query due jobs from database
    try:
        due_jobs = await scheduled_job_repo.get_due_jobs(cutoff_time=now, limit=batch_size)
    except Exception as e:
        logger.error(
            "scheduled_job_query_failed",
            error=str(e),
            reason="Failed to query due scheduled jobs from database",
        )
        return 0

    if not due_jobs:
        logger.debug("no_due_jobs", cutoff_time=now.isoformat())
        return 0

    logger.info("processing_due_jobs", job_count=len(due_jobs), cutoff_time=now.isoformat())

    # Process each due job
    for scheduled_job in due_jobs:
        try:
            # Note: We could check if previous job is still running by querying recent jobs
            # with metadata.scheduled_job_id, but for simplicity we'll allow concurrent runs.
            # This is acceptable as each job is independent and workers can handle concurrent
            # crawls of the same website (with different job IDs).

            # Fetch website to get base_url (used as seed_url)
            website = await website_repo.get_by_id(str(scheduled_job.website_id))

            # Guard: website not found or deleted
            if not website or website.deleted_at is not None:
                logger.error(
                    "website_not_found_for_scheduled_job",
                    scheduled_job_id=str(scheduled_job.id),
                    website_id=str(scheduled_job.website_id),
                    reason="Website deleted or not found - deactivating scheduled job",
                )
                # Deactivate scheduled job since website no longer exists
                await scheduled_job_repo.toggle_status(
                    job_id=str(scheduled_job.id), is_active=False
                )
                continue

            # Prepare job: handle timezone backfill and orphaned state
            job_timezone, should_continue = await _prepare_scheduled_job(
                scheduled_job, scheduled_job_repo, now
            )
            if not should_continue:
                continue

            # Create and publish crawl job using helper function
            crawl_job_id = await _create_and_publish_crawl_job(
                crawl_job_repo=crawl_job_repo,
                nats_queue=nats_queue,
                website_id=str(scheduled_job.website_id),
                seed_url=website.base_url,
                job_config=scheduled_job.job_config,
                scheduled_job_id=str(scheduled_job.id),
                cron_schedule=scheduled_job.cron_schedule,
                now=now,
                is_catchup=False,
                missed_time=None,
            )

            # Guard: job creation or publishing failed
            if not crawl_job_id:
                continue

            # Calculate next run time from cron expression in job's timezone
            # (job_timezone already extracted above for orphaned job guard)
            try:
                next_run_time = calculate_next_run(
                    scheduled_job.cron_schedule, now, timezone=job_timezone
                )
            except ValueError as e:
                logger.error(
                    "cron_calculation_failed",
                    scheduled_job_id=str(scheduled_job.id),
                    cron_schedule=scheduled_job.cron_schedule,
                    timezone=job_timezone,
                    error=str(e),
                    reason="Invalid cron expression - job will not be rescheduled",
                )
                # Deactivate job if cron is invalid
                await scheduled_job_repo.toggle_status(
                    job_id=str(scheduled_job.id), is_active=False
                )
                continue

            # Check for DST transition in the job's timezone
            dst_transition = get_dst_transition_type(next_run_time, job_timezone)
            if dst_transition:
                logger.info(
                    "dst_transition_detected",
                    scheduled_job_id=str(scheduled_job.id),
                    next_run_time=next_run_time.isoformat(),
                    transition_type=dst_transition,
                    timezone=job_timezone,
                    note="DST transition detected - next run time adjusted automatically",
                )

            # Update scheduled job with next run time
            await scheduled_job_repo.update_next_run(
                job_id=str(scheduled_job.id),
                next_run_time=next_run_time,
                last_run_time=now,
            )

            logger.info(
                "scheduled_job_processed",
                scheduled_job_id=str(scheduled_job.id),
                crawl_job_id=crawl_job_id,
                website_id=str(scheduled_job.website_id),
                seed_url=website.base_url,
                next_run_time=next_run_time.isoformat(),
                cron_schedule=scheduled_job.cron_schedule,
            )

            processed_count += 1
            scheduled_jobs_processed_total.labels(processing_type="normal").inc()

        except Exception as e:
            logger.error(
                "scheduled_job_processing_error",
                scheduled_job_id=str(scheduled_job.id),
                error=str(e),
                exc_info=True,
                reason="Unexpected error processing scheduled job - continuing with next job",
            )
            continue

    logger.info("batch_processing_complete", processed_count=processed_count, total=len(due_jobs))
    return processed_count


async def scheduled_job_processor_loop(
    scheduled_job_repo: ScheduledJobRepository,
    crawl_job_repo: CrawlJobRepository,
    website_repo: WebsiteRepository,
    nats_queue: NATSQueueService,
    interval_seconds: int = 60,
    batch_size: int = 100,
) -> None:
    """Background loop that periodically processes scheduled jobs.

    Args:
        scheduled_job_repo: Repository for scheduled job operations
        crawl_job_repo: Repository for crawl job operations
        website_repo: Repository for website operations
        nats_queue: NATS queue service for job publishing
        interval_seconds: Sleep duration between polling cycles (default: 60s)
        batch_size: Maximum jobs to process per cycle (default: 100)

    This loop runs continuously until cancelled:
    - On first run: handles missed schedules from downtime
    - Polls database every interval_seconds
    - Processes all due jobs in batches
    - Handles errors gracefully and continues
    - Supports graceful shutdown via asyncio.CancelledError
    """
    logger.info(
        "scheduled_job_processor_started",
        interval_seconds=interval_seconds,
        batch_size=batch_size,
    )

    # First run: handle missed schedules after restart
    first_run = True

    while True:
        try:
            if first_run:
                # Handle missed schedules on startup
                try:
                    caught_up, skipped = await handle_missed_schedules(
                        scheduled_job_repo=scheduled_job_repo,
                        crawl_job_repo=crawl_job_repo,
                        website_repo=website_repo,
                        nats_queue=nats_queue,
                        batch_size=batch_size,
                    )
                    logger.info(
                        "missed_schedule_catchup_complete",
                        caught_up=caught_up,
                        skipped=skipped,
                    )
                except Exception as e:
                    logger.error(
                        "missed_schedule_catchup_failed",
                        error=str(e),
                        exc_info=True,
                        reason=(
                            "Failed to handle missed schedules - continuing with normal processing"
                        ),
                    )
                first_run = False

            # Normal scheduled job processing
            await process_scheduled_jobs(
                scheduled_job_repo=scheduled_job_repo,
                crawl_job_repo=crawl_job_repo,
                website_repo=website_repo,
                nats_queue=nats_queue,
                batch_size=batch_size,
            )
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("scheduled_job_processor_cancelled")
            break
        except Exception as e:
            logger.error(
                "scheduled_job_processor_error",
                error=str(e),
                exc_info=True,
                reason="Unexpected error in processor loop - continuing after sleep",
            )
            await asyncio.sleep(interval_seconds)


async def start_scheduled_job_processor(
    scheduled_job_repo: ScheduledJobRepository,
    crawl_job_repo: CrawlJobRepository,
    website_repo: WebsiteRepository,
    nats_queue: NATSQueueService,
    interval_seconds: int = 60,
    batch_size: int = 100,
) -> None:
    """Start the scheduled job processor background task.

    Args:
        scheduled_job_repo: Repository for scheduled job operations
        crawl_job_repo: Repository for crawl job operations
        website_repo: Repository for website operations
        nats_queue: NATS queue service for job publishing
        interval_seconds: Sleep duration between polling cycles (default: 60s)
        batch_size: Maximum jobs to process per cycle (default: 100)

    Raises:
        Warning: If processor is already running (logs warning, does not raise)

    This should be called during application startup (in FastAPI lifespan).
    """
    global _processor_task

    # Guard: already running
    if _processor_task is not None and not _processor_task.done():
        logger.warning("scheduled_job_processor_already_running")
        return

    _processor_task = asyncio.create_task(
        scheduled_job_processor_loop(
            scheduled_job_repo=scheduled_job_repo,
            crawl_job_repo=crawl_job_repo,
            website_repo=website_repo,
            nats_queue=nats_queue,
            interval_seconds=interval_seconds,
            batch_size=batch_size,
        )
    )
    logger.info("scheduled_job_processor_task_created")


async def stop_scheduled_job_processor() -> None:
    """Stop the scheduled job processor background task.

    Gracefully cancels the task and waits for it to finish.
    Safe to call even if task is not running.

    This should be called during application shutdown (in FastAPI lifespan).
    """
    global _processor_task

    # Guard: not running
    if _processor_task is None:
        logger.warning("scheduled_job_processor_not_running")
        return

    _processor_task.cancel()
    try:
        await _processor_task
    except asyncio.CancelledError:
        pass

    _processor_task = None
    logger.info("scheduled_job_processor_stopped")
