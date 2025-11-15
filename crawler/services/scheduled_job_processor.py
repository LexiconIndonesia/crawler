"""Scheduled job processor for creating crawl jobs from scheduled jobs.

This module provides a background service that:
1. Polls the database for scheduled jobs that are due
2. Creates crawl jobs for each due scheduled job
3. Publishes the jobs to NATS queue for workers to pick up
4. Updates the next_run_time for recurring jobs
5. Handles graceful shutdown and restart
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from crawler.core.logging import get_logger
from crawler.core.metrics import scheduled_jobs_processed_total
from crawler.db.generated.models import JobTypeEnum, StatusEnum
from crawler.utils.cron import calculate_next_run

if TYPE_CHECKING:
    from crawler.db.repositories.crawl_job import CrawlJobRepository
    from crawler.db.repositories.scheduled_job import ScheduledJobRepository
    from crawler.db.repositories.website import WebsiteRepository
    from crawler.services.nats_queue import NATSQueueService

logger = get_logger(__name__)

# Global task reference for lifecycle management
_processor_task: asyncio.Task | None = None


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

            # Create crawl job from scheduled job using website base_url as seed
            # Priority 5 = normal scheduled jobs (within 4-6 range as per requirements)
            crawl_job = await crawl_job_repo.create_template_based_job(
                website_id=str(scheduled_job.website_id),
                seed_url=website.base_url,  # Use website base_url as seed_url
                variables=scheduled_job.job_config or {},  # Use job_config as variables
                job_type=JobTypeEnum.SCHEDULED,
                priority=5,  # PRIORITY_SCHEDULED - normal scheduled jobs
                scheduled_at=now,
                max_retries=3,  # Default retry count
                metadata={
                    "scheduled_job_id": str(scheduled_job.id),
                    "cron_schedule": scheduled_job.cron_schedule,
                },
            )

            # Guard: job creation failed
            if not crawl_job:
                logger.error(
                    "crawl_job_creation_failed",
                    scheduled_job_id=str(scheduled_job.id),
                    website_id=str(scheduled_job.website_id),
                    reason="create_template_based_job returned None",
                )
                continue

            # Publish job to NATS queue
            job_data = {
                "website_id": str(crawl_job.website_id) if crawl_job.website_id else None,
                "seed_url": crawl_job.seed_url,
                "job_type": crawl_job.job_type.value,
                "priority": crawl_job.priority,
            }
            published = await nats_queue.publish_job(str(crawl_job.id), job_data)

            # Guard: publish failed
            if not published:
                logger.error(
                    "job_publish_failed",
                    crawl_job_id=str(crawl_job.id),
                    scheduled_job_id=str(scheduled_job.id),
                    reason="NATS queue publish returned False",
                )
                # Mark job as failed since it wasn't enqueued
                await crawl_job_repo.update_status(
                    job_id=str(crawl_job.id), status=StatusEnum.FAILED
                )
                continue

            # Calculate next run time from cron expression
            try:
                next_run_time = calculate_next_run(scheduled_job.cron_schedule, now)
            except ValueError as e:
                logger.error(
                    "cron_calculation_failed",
                    scheduled_job_id=str(scheduled_job.id),
                    cron_schedule=scheduled_job.cron_schedule,
                    error=str(e),
                    reason="Invalid cron expression - job will not be rescheduled",
                )
                # Deactivate job if cron is invalid
                await scheduled_job_repo.toggle_status(
                    job_id=str(scheduled_job.id), is_active=False
                )
                continue

            # Update scheduled job with next run time
            await scheduled_job_repo.update_next_run(
                job_id=str(scheduled_job.id),
                next_run_time=next_run_time,
                last_run_time=now,
            )

            logger.info(
                "scheduled_job_processed",
                scheduled_job_id=str(scheduled_job.id),
                crawl_job_id=str(crawl_job.id),
                website_id=str(scheduled_job.website_id),
                seed_url=website.base_url,
                next_run_time=next_run_time.isoformat(),
                cron_schedule=scheduled_job.cron_schedule,
            )

            processed_count += 1
            scheduled_jobs_processed_total.inc()

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

    while True:
        try:
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
