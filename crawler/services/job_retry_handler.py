"""Job retry handler for automatic retry on transient failures.

This module provides:
1. Error classification and retry decision logic
2. Retry attempt tracking and history recording
3. Backoff delay calculation with jitter
4. Integration with retry policies from database
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from uuid import UUID

from crawler.core import metrics
from crawler.core.logging import get_logger
from crawler.db.generated.models import CrawlJob, ErrorCategoryEnum, StatusEnum
from crawler.db.repositories import (
    CrawlJobRepository,
    DeadLetterQueueRepository,
    RetryHistoryRepository,
    RetryPolicyRepository,
)
from crawler.services.retry_policy import (
    RetryPolicyService,
    calculate_backoff,
    get_error_context,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncConnection

    from crawler.services.nats_queue import NATSQueueService

logger = get_logger(__name__)


class JobRetryHandler:
    """Handles automatic retry logic for failed jobs."""

    def __init__(
        self,
        job_repo: CrawlJobRepository,
        retry_policy_repo: RetryPolicyRepository,
        retry_history_repo: RetryHistoryRepository,
        dlq_repo: DeadLetterQueueRepository,
        nats_queue: NATSQueueService,
    ):
        """Initialize retry handler.

        Args:
            job_repo: Repository for job operations
            retry_policy_repo: Repository for retry policy lookups
            retry_history_repo: Repository for tracking retry attempts
            dlq_repo: Repository for dead letter queue operations
            nats_queue: NATS queue service for requeueing jobs
        """
        self.job_repo = job_repo
        self.retry_policy_service = RetryPolicyService(retry_policy_repo)
        self.retry_history_repo = retry_history_repo
        self.dlq_repo = dlq_repo
        self.nats_queue = nats_queue

    async def should_retry(
        self,
        job_id: str | UUID,
        exc: Exception | None = None,
        http_status: int | None = None,
        retry_after: str | None = None,
    ) -> tuple[bool, ErrorCategoryEnum, int]:
        """Determine if job should be retried.

        Args:
            job_id: Job ID to check
            exc: Optional exception that caused failure
            http_status: Optional HTTP status code
            retry_after: Optional Retry-After header value

        Returns:
            Tuple of (should_retry, error_category, delay_seconds)
        """
        # Get current job state
        job = await self.job_repo.get_by_id(str(job_id))

        # Guard: job not found
        if not job:
            logger.error("retry_check_job_not_found", job_id=str(job_id))
            return (False, ErrorCategoryEnum.UNKNOWN, 0)

        # Classify the error and get retry policy
        (
            error_category,
            is_retryable,
            max_attempts,
            _,  # initial_delay not used (calculated later with jitter)
        ) = await self.retry_policy_service.get_policy_for_error(exc=exc, http_status=http_status)

        logger.info(
            "retry_policy_evaluated",
            job_id=str(job_id),
            error_category=error_category.value,
            is_retryable=is_retryable,
            retry_count=job.retry_count,
            max_attempts=max_attempts,
        )

        # Guard: error is not retryable
        if not is_retryable:
            logger.info(
                "error_not_retryable",
                job_id=str(job_id),
                error_category=error_category.value,
            )
            return (False, error_category, 0)

        # Guard: max attempts exceeded
        if job.retry_count >= max_attempts:
            logger.info(
                "max_retry_attempts_exceeded",
                job_id=str(job_id),
                retry_count=job.retry_count,
                max_attempts=max_attempts,
            )
            return (False, error_category, 0)

        # Calculate delay for next retry
        delay = await self.retry_policy_service.calculate_next_delay(
            error_category, job.retry_count + 1
        )

        # Get policy for backoff strategy and apply jitter
        policy = await self.retry_policy_service.retry_policy_repo.get_by_category(error_category)

        if policy:
            delay = calculate_backoff(
                strategy=policy.backoff_strategy,
                attempt=job.retry_count + 1,
                initial_delay=policy.initial_delay_seconds,
                max_delay=policy.max_delay_seconds,
                multiplier=policy.backoff_multiplier,
                apply_jitter=True,  # Always use jitter to avoid thundering herd
                jitter_percent=0.2,  # 20% jitter
                retry_after=retry_after,  # Respect server's Retry-After header
            )

        logger.info(
            "retry_approved",
            job_id=str(job_id),
            retry_count=job.retry_count,
            next_attempt=job.retry_count + 1,
            delay_seconds=delay,
        )

        return (True, error_category, delay)

    async def record_retry_attempt(
        self,
        job_id: str | UUID,
        error_category: ErrorCategoryEnum,
        error_message: str,
        delay_seconds: int,
        exc: Exception | None = None,
    ) -> None:
        """Record a retry attempt in history.

        Args:
            job_id: Job ID
            error_category: Category of the error
            error_message: Error message
            delay_seconds: Delay before next retry
            exc: Optional exception for stack trace
        """
        # Get current retry count
        job = await self.job_repo.get_by_id(str(job_id))
        if not job:
            logger.error("record_retry_job_not_found", job_id=str(job_id))
            return

        # Extract stack trace if exception provided
        stack_trace = None
        if exc:
            context = get_error_context(exc)
            stack_trace = context.get("stack_trace")

        # Record in retry history
        await self.retry_history_repo.create(
            job_id=job_id,
            attempt_number=job.retry_count + 1,
            error_category=error_category,
            error_message=error_message,
            retry_delay_seconds=delay_seconds,
            stack_trace=stack_trace,
        )

        logger.info(
            "retry_attempt_recorded",
            job_id=str(job_id),
            attempt_number=job.retry_count + 1,
            error_category=error_category.value,
        )

    async def handle_job_failure(
        self,
        job_id: str | UUID,
        exc: Exception | None = None,
        http_status: int | None = None,
        error_message: str | None = None,
        retry_after: str | None = None,
    ) -> bool:
        """Handle job failure and decide whether to retry.

        Args:
            job_id: Job ID that failed
            exc: Optional exception that caused failure
            http_status: Optional HTTP status code
            error_message: Error message
            retry_after: Optional Retry-After header value

        Returns:
            True if job will be retried, False if permanently failed
        """
        # Check if should retry
        should_retry, error_category, delay = await self.should_retry(
            job_id, exc=exc, http_status=http_status, retry_after=retry_after
        )

        # Prepare error message
        if not error_message:
            error_message = str(exc) if exc else "Unknown error"

        if should_retry:
            # Record retry attempt
            await self.record_retry_attempt(
                job_id,
                error_category,
                error_message[:1000],  # Truncate to DB limit
                delay,
                exc=exc,
            )
            # Increment retry count
            job = await self.job_repo.get_by_id(str(job_id))
            if not job:
                logger.error("job_not_found_for_retry", job_id=str(job_id))
                return False

            await self.job_repo.update_retry_count(
                job_id=str(job_id), retry_count=job.retry_count + 1
            )

            # Update job status to pending (will be retried)
            await self.job_repo.update_status(
                job_id=str(job_id),
                status=StatusEnum.PENDING,
                started_at=None,
                completed_at=None,
                error_message=f"Retry {job.retry_count + 1}: {error_message[:900]}",
            )

            # Schedule retry with delay
            if delay > 0:
                logger.info(
                    "scheduling_delayed_retry",
                    job_id=str(job_id),
                    delay_seconds=delay,
                )
                # Sleep before requeueing
                await asyncio.sleep(delay)

            # Requeue job
            try:
                await self.nats_queue.publish_job(str(job_id), {"job_id": str(job_id)})
            except Exception as e:
                logger.error(
                    "failed_to_requeue_job",
                    job_id=str(job_id),
                    error=str(e),
                    exc_info=True,
                )
                # Revert job status since we couldn't queue it
                await self.job_repo.update_status(
                    job_id=str(job_id),
                    status=StatusEnum.FAILED,
                    error_message=f"Failed to requeue: {str(e)}",
                )
                return False

            logger.info(
                "job_requeued_for_retry",
                job_id=str(job_id),
                retry_count=job.retry_count + 1,
                delay_seconds=delay,
            )

            return True
        else:
            # Max retries exceeded or non-retryable error - move to DLQ
            await self.job_repo.update_status(
                job_id=str(job_id),
                status=StatusEnum.FAILED,
                error_message=error_message[:1000],
            )

            job = await self.job_repo.get_by_id(str(job_id))
            if job:
                # Add to dead letter queue for manual review
                await self._add_to_dlq(
                    job=job,
                    error_category=error_category,
                    error_message=error_message,
                    exc=exc,
                    http_status=http_status,
                )

            logger.warning(
                "job_permanently_failed_moved_to_dlq",
                job_id=str(job_id),
                error_category=error_category.value,
                retry_count=job.retry_count if job else 0,
            )

            return False

    async def _add_to_dlq(
        self,
        job: CrawlJob,
        error_category: ErrorCategoryEnum,
        error_message: str,
        exc: Exception | None = None,
        http_status: int | None = None,
    ) -> None:
        """Add a permanently failed job to the dead letter queue.

        Args:
            job: The failed job
            error_category: Category of error
            error_message: Error message
            exc: Optional exception
            http_status: Optional HTTP status code
        """
        # Get retry history to extract timing information
        retry_history = await self.retry_history_repo.get_by_job_id(str(job.id))

        # Calculate timing information
        first_attempt_at = job.created_at
        last_attempt_at = job.updated_at
        total_attempts = job.retry_count + 1  # Include initial attempt

        if retry_history:
            # Use last retry attempt timestamp for last_attempt_at
            last_attempt_at = retry_history[-1].attempted_at

        # Extract stack trace if exception provided
        stack_trace = None
        if exc:
            context = get_error_context(exc)
            stack_trace = context.get("stack_trace")

        # Add to DLQ
        try:
            dlq_entry = await self.dlq_repo.add_to_dlq(
                job_id=str(job.id),
                seed_url=str(job.seed_url),
                website_id=str(job.website_id) if job.website_id else None,
                job_type=job.job_type,
                priority=job.priority,
                error_category=error_category,
                error_message=error_message[:1000],
                stack_trace=stack_trace,
                http_status=http_status,
                total_attempts=total_attempts,
                first_attempt_at=first_attempt_at,
                last_attempt_at=last_attempt_at,
            )

            logger.info(
                "job_added_to_dlq",
                job_id=str(job.id),
                dlq_id=dlq_entry.id,
                error_category=error_category.value,
                total_attempts=total_attempts,
            )

            # Emit DLQ metrics

            metrics.dlq_entries_total.labels(
                error_category=error_category.value, job_type=job.job_type.value
            ).inc()
        except Exception as e:
            # Log error but don't fail the job permanently
            logger.error(
                "failed_to_add_job_to_dlq",
                job_id=str(job.id),
                error=str(e),
                exc_info=True,
            )


async def create_retry_handler(
    conn: AsyncConnection, nats_queue: NATSQueueService
) -> JobRetryHandler:
    """Factory function to create JobRetryHandler with repositories.

    Args:
        conn: Database connection
        nats_queue: NATS queue service

    Returns:
        Configured JobRetryHandler instance
    """
    job_repo = CrawlJobRepository(conn)
    retry_policy_repo = RetryPolicyRepository(conn)
    retry_history_repo = RetryHistoryRepository(conn)
    dlq_repo = DeadLetterQueueRepository(conn)

    return JobRetryHandler(job_repo, retry_policy_repo, retry_history_repo, dlq_repo, nats_queue)
