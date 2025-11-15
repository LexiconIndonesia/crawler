"""Retry scheduler service that polls Redis and enqueues jobs ready for retry.

This service runs as a background task and periodically checks the Redis sorted set
for jobs whose retry time has arrived, then publishes them to the NATS queue.
"""

import asyncio

from crawler.core.logging import get_logger
from crawler.services.nats_queue import NATSQueueService
from crawler.services.retry_scheduler_cache import RetrySchedulerCache

logger = get_logger(__name__)

# Global task reference
_scheduler_task: asyncio.Task | None = None


async def retry_scheduler_loop(
    retry_cache: RetrySchedulerCache,
    nats_queue: NATSQueueService,
    interval_seconds: int = 5,
    batch_size: int = 100,
) -> None:
    """Background loop that polls Redis and enqueues ready jobs.

    Args:
        retry_cache: Redis cache with scheduled retries
        nats_queue: NATS queue service for publishing jobs
        interval_seconds: Polling interval in seconds (default: 5)
        batch_size: Maximum jobs to process per iteration (default: 100)
    """
    logger.info(
        "retry_scheduler_started",
        interval_seconds=interval_seconds,
        batch_size=batch_size,
    )

    while True:
        try:
            # Get jobs ready for retry
            ready_job_ids = await retry_cache.get_ready_jobs(limit=batch_size)

            if ready_job_ids:
                logger.info(
                    "processing_ready_retries",
                    count=len(ready_job_ids),
                )

                # Enqueue each job
                for job_id in ready_job_ids:
                    try:
                        # Publish to NATS
                        success = await nats_queue.publish_job(job_id, {"job_id": job_id})

                        if success:
                            # Remove from schedule
                            await retry_cache.remove_scheduled(job_id)
                            logger.debug("retry_enqueued", job_id=job_id)
                        else:
                            logger.error(
                                "failed_to_enqueue_retry",
                                job_id=job_id,
                            )
                            # Don't remove from schedule - will retry next iteration

                    except Exception as e:
                        logger.error(
                            "error_enqueueing_retry",
                            job_id=job_id,
                            error=str(e),
                            exc_info=True,
                        )
                        # Don't remove from schedule - will retry next iteration

                logger.info(
                    "retry_batch_processed",
                    processed=len(ready_job_ids),
                )

            # Sleep before next poll
            await asyncio.sleep(interval_seconds)

        except asyncio.CancelledError:
            logger.info("retry_scheduler_cancelled")
            break
        except Exception as e:
            logger.error(
                "retry_scheduler_error",
                error=str(e),
                exc_info=True,
            )
            # Continue after error
            await asyncio.sleep(interval_seconds)


async def start_retry_scheduler(
    retry_cache: RetrySchedulerCache,
    nats_queue: NATSQueueService,
    interval_seconds: int = 5,
    batch_size: int = 100,
) -> None:
    """Start the retry scheduler background task.

    Args:
        retry_cache: Redis cache with scheduled retries
        nats_queue: NATS queue service for publishing jobs
        interval_seconds: Polling interval in seconds (default: 5)
        batch_size: Maximum jobs to process per iteration (default: 100)
    """
    global _scheduler_task

    if _scheduler_task is not None and not _scheduler_task.done():
        logger.warning("retry_scheduler_already_running")
        return

    _scheduler_task = asyncio.create_task(
        retry_scheduler_loop(retry_cache, nats_queue, interval_seconds, batch_size)
    )
    logger.info("retry_scheduler_task_created")


async def stop_retry_scheduler() -> None:
    """Stop the retry scheduler background task."""
    global _scheduler_task

    if _scheduler_task is None:
        logger.warning("retry_scheduler_not_running")
        return

    _scheduler_task.cancel()
    try:
        await _scheduler_task
    except asyncio.CancelledError:
        pass

    _scheduler_task = None
    logger.info("retry_scheduler_stopped")
