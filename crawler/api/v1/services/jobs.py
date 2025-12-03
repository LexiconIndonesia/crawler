"""Job service with business logic."""

from typing import Any

from pydantic import AnyUrl

from crawler.api.generated import (
    CancelJobRequest,
    CancelJobResponse,
    CrawlJobStatus,
    CreateSeedJobInlineRequest,
    CreateSeedJobRequest,
    JobType,
    SeedJobResponse,
)
from crawler.api.generated.models import JobStatusEnum
from crawler.core.logging import get_logger
from crawler.db.generated.models import JobTypeEnum, StatusEnum
from crawler.db.repositories import CrawlJobRepository, WebsiteRepository
from crawler.services.nats_queue import NATSQueueService
from crawler.services.redis_cache import JobCancellationFlag
from crawler.utils import normalize_url

logger = get_logger(__name__)


def _safe_convert_status(db_status: StatusEnum) -> JobStatusEnum:
    """Convert database StatusEnum to API JobStatusEnum.

    Args:
        db_status: Database status enum

    Returns:
        API job status enum

    Raises:
        ValueError: If db_status cannot be mapped to a valid API JobStatusEnum.
            This indicates a schema mismatch between the database and API that
            must be resolved before the system can operate correctly.
    """
    try:
        return JobStatusEnum(db_status.value)
    except ValueError as e:
        logger.error(
            "unmapped_job_status",
            db_status=db_status,
            db_status_value=db_status.value,
        )
        raise ValueError(
            f"Cannot map database status '{db_status.value}' to API JobStatusEnum. "
            f"This indicates a schema mismatch that must be resolved."
        ) from e


def _safe_convert_job_type(db_job_type: JobTypeEnum) -> JobType:
    """Convert database JobTypeEnum to API JobType.

    Args:
        db_job_type: Database job type enum

    Returns:
        API job type enum

    Raises:
        ValueError: If db_job_type cannot be mapped to a valid API JobType.
            This indicates a schema mismatch between the database and API that
            must be resolved before the system can operate correctly.
    """
    try:
        return JobType(db_job_type.value)
    except ValueError as e:
        logger.error(
            "unmapped_job_type",
            db_job_type=db_job_type,
            db_job_type_value=db_job_type.value,
        )
        raise ValueError(
            f"Cannot map database job type '{db_job_type.value}' to API JobType. "
            f"This indicates a schema mismatch that must be resolved."
        ) from e


class JobService:
    """Service for crawl job operations with dependency injection."""

    def __init__(
        self,
        crawl_job_repo: CrawlJobRepository,
        website_repo: WebsiteRepository,
        cancellation_flag: JobCancellationFlag,
        nats_queue: NATSQueueService,
    ):
        """Initialize service with dependencies.

        Args:
            crawl_job_repo: Crawl job repository for database access
            website_repo: Website repository for template loading
            cancellation_flag: Job cancellation flag service for Redis operations
            nats_queue: NATS queue service for job queuing
        """
        self.crawl_job_repo = crawl_job_repo
        self.website_repo = website_repo
        self.cancellation_flag = cancellation_flag
        self.nats_queue = nats_queue

    async def create_seed_job(self, request: CreateSeedJobRequest) -> SeedJobResponse:
        """Create a new crawl job using a website template.

        This method:
        1. Validates that the website template exists
        2. Checks that the website is active
        3. Creates a template-based crawl job with the seed URL
        4. Returns the job details

        Args:
            request: Seed job creation request

        Returns:
            Created seed job response

        Raises:
            ValueError: If website not found or inactive
            RuntimeError: If job creation fails
        """
        logger.info(
            "creating_seed_job",
            website_id=str(request.website_id),
            seed_url=str(request.seed_url),
            priority=request.priority,
        )

        # Normalize the seed URL for consistent storage and deduplication
        try:
            normalized_seed_url = normalize_url(str(request.seed_url))
            logger.debug(
                "seed_url_normalized",
                original_url=str(request.seed_url),
                normalized_url=normalized_seed_url,
            )
        except ValueError as e:
            logger.warning("invalid_seed_url", seed_url=str(request.seed_url), error=str(e))
            raise ValueError(f"Invalid seed URL: {e}") from e

        # Load website template from database
        website = await self.website_repo.get_by_id(request.website_id)
        if not website:
            logger.warning("website_not_found", website_id=str(request.website_id))
            raise ValueError(f"Website with ID '{request.website_id}' not found")

        # Check if website is active
        if website.status != StatusEnum.ACTIVE:
            logger.warning(
                "website_inactive",
                website_id=str(request.website_id),
                website_name=website.name,
                status=website.status.value,
            )
            raise ValueError(f"Website '{website.name}' is inactive and cannot be used")

        # Extract max_retries from website config if available
        max_retries = 3  # Default
        if isinstance(website.config, dict):
            global_config = website.config.get("global_config", {})
            if isinstance(global_config, dict):
                retry_config = global_config.get("retry", {})
                if isinstance(retry_config, dict):
                    max_attempts = retry_config.get("max_attempts")
                    if max_attempts is not None:
                        max_retries = max_attempts

        logger.debug(
            "max_retries_set_from_template",
            website_id=str(request.website_id),
            max_retries=max_retries,
        )

        # Create template-based job
        # Use normalized seed URL for database storage
        job = await self.crawl_job_repo.create_template_based_job(
            website_id=request.website_id,
            seed_url=normalized_seed_url,
            variables=request.variables,
            job_type=JobTypeEnum.ONE_TIME,  # Seed submissions are always one-time jobs
            priority=request.priority,
            scheduled_at=None,  # Seed jobs execute immediately (not scheduled)
            max_retries=max_retries,
            metadata=None,
        )

        if not job:
            logger.error(
                "job_creation_failed",
                website_id=str(request.website_id),
                seed_url=str(request.seed_url),
            )
            raise RuntimeError("Failed to create crawl job")

        logger.info(
            "seed_job_created",
            job_id=str(job.id),
            website_id=str(request.website_id),
            seed_url=str(request.seed_url),
            priority=job.priority,
        )

        # Publish job to NATS queue for workers to pick up
        job_data = {
            "website_id": str(job.website_id) if job.website_id else None,
            "seed_url": job.seed_url,
            "job_type": job.job_type.value,
            "priority": job.priority,
        }
        published = await self.nats_queue.publish_job(str(job.id), job_data)

        if not published:
            logger.warning(
                "job_publish_to_queue_failed",
                job_id=str(job.id),
                reason="nats_publish_failed_but_job_created_in_db",
            )
            # Note: Job is still created in DB even if queue publish fails
            # Worker can still pick it up via database polling as fallback

        # Build response - convert database enum to API enum (with safe fallbacks)
        api_status = _safe_convert_status(job.status)
        job_type = _safe_convert_job_type(job.job_type)

        # Ensure website_id is not None (it shouldn't be for template-based jobs)
        assert job.website_id is not None, "website_id should not be None for template-based jobs"

        return SeedJobResponse(
            id=job.id,
            website_id=job.website_id,
            seed_url=AnyUrl(job.seed_url),
            status=CrawlJobStatus(job_id=job.id, status=api_status),
            job_type=job_type,
            priority=job.priority,
            scheduled_at=job.scheduled_at,
            variables=job.variables,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def create_seed_job_inline(self, request: CreateSeedJobInlineRequest) -> SeedJobResponse:
        """Create a new crawl job with inline configuration.

        This method:
        1. Validates the inline configuration
        2. Creates an inline config job (no website template)
        3. Returns the job details

        Args:
            request: Seed job creation request with inline configuration

        Returns:
            Created seed job response

        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If job creation fails
        """
        logger.info(
            "creating_seed_job_inline",
            seed_url=str(request.seed_url),
            priority=request.priority,
            num_steps=len(request.steps),
        )

        # Normalize the seed URL for consistent storage and deduplication
        try:
            normalized_seed_url = normalize_url(str(request.seed_url))
            logger.debug(
                "seed_url_normalized",
                original_url=str(request.seed_url),
                normalized_url=normalized_seed_url,
            )
        except ValueError as e:
            logger.warning("invalid_seed_url", seed_url=str(request.seed_url), error=str(e))
            raise ValueError(f"Invalid seed URL: {e}") from e

        # Build inline configuration from request
        # Convert Pydantic models to dict for JSON storage
        inline_config: dict[str, Any] = {
            "steps": [step.model_dump(mode="json", exclude_none=True) for step in request.steps],
            "global_config": request.global_config.model_dump(mode="json", exclude_none=True),
        }

        logger.debug(
            "inline_config_prepared",
            seed_url=str(request.seed_url),
            config_keys=list(inline_config.keys()),
            steps_count=len(inline_config["steps"]),
        )

        # Extract max_retries from global_config.retry.max_attempts if available
        max_retries = 3  # Default
        if request.global_config.retry and request.global_config.retry.max_attempts is not None:
            max_retries = request.global_config.retry.max_attempts

        logger.debug(
            "max_retries_set",
            seed_url=str(request.seed_url),
            max_retries=max_retries,
            from_config=request.global_config.retry is not None,
        )

        # Create inline config job (no website_id)
        # Use normalized seed URL for database storage
        job = await self.crawl_job_repo.create_seed_url_submission(
            seed_url=normalized_seed_url,
            inline_config=inline_config,
            variables=request.variables,
            job_type=JobTypeEnum.ONE_TIME,  # Inline submissions are always one-time jobs
            priority=request.priority,
            scheduled_at=None,  # Inline jobs execute immediately (not scheduled)
            max_retries=max_retries,
            metadata=None,
        )

        if not job:
            logger.error(
                "job_creation_failed",
                seed_url=str(request.seed_url),
            )
            raise RuntimeError("Failed to create crawl job")

        logger.info(
            "seed_job_inline_created",
            job_id=str(job.id),
            seed_url=str(request.seed_url),
            priority=job.priority,
        )

        # Publish job to NATS queue for workers to pick up
        job_data = {
            "website_id": None,  # Inline config jobs don't have website_id
            "seed_url": job.seed_url,
            "job_type": job.job_type.value,
            "priority": job.priority,
            "has_inline_config": True,
        }
        published = await self.nats_queue.publish_job(str(job.id), job_data)

        if not published:
            logger.warning(
                "job_publish_to_queue_failed",
                job_id=str(job.id),
                reason="nats_publish_failed_but_job_created_in_db",
            )
            # Note: Job is still created in DB even if queue publish fails
            # Worker can still pick it up via database polling as fallback

        # Build response - convert database enum to API enum (with safe fallbacks)
        api_status = _safe_convert_status(job.status)
        job_type = _safe_convert_job_type(job.job_type)

        return SeedJobResponse(
            id=job.id,
            website_id=None,  # Inline config jobs don't have website_id
            seed_url=AnyUrl(job.seed_url),
            status=CrawlJobStatus(job_id=job.id, status=api_status),
            job_type=job_type,
            priority=job.priority,
            scheduled_at=job.scheduled_at,
            variables=job.variables,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def cancel_job(self, job_id: str, request: CancelJobRequest) -> CancelJobResponse:
        """Cancel a crawl job with atomic database operation.

        This method:
        1. Validates that the job exists
        2. Sets a Redis cancellation flag for workers to detect
        3. Atomically updates the job status to "cancelled" (only if pending/running)
        4. Returns the updated job information

        The cancellation is idempotent - if the job is already cancelled, it returns
        success. If the job is in a final state (completed/failed), it raises an error.

        Args:
            job_id: Job ID to cancel
            request: Cancellation request with optional reason

        Returns:
            Cancellation response with updated job status

        Raises:
            ValueError: If job not found or cannot be cancelled (completed/failed)
            RuntimeError: If cancellation operation fails unexpectedly
        """
        logger.info(
            "cancelling_job",
            job_id=job_id,
            reason=request.reason,
        )

        # Get the job to verify it exists
        job = await self.crawl_job_repo.get_by_id(job_id)
        if not job:
            logger.warning("job_not_found", job_id=job_id)
            raise ValueError(f"Job with ID '{job_id}' not found")

        # Set Redis cancellation flag for workers to detect
        # Do this BEFORE database update so workers can detect cancellation immediately
        flag_set = await self.cancellation_flag.set_cancellation(
            job_id=job_id,
            reason=request.reason,
        )

        if not flag_set:
            logger.error("failed_to_set_cancellation_flag", job_id=job_id)
            raise RuntimeError("Failed to set cancellation flag in Redis")

        # Remove job from NATS queue if it's pending (not yet started)
        # This provides immediate cancellation for queued jobs
        if job.status == StatusEnum.PENDING:
            removed = await self.nats_queue.delete_job_from_queue(job_id)
            if removed:
                logger.info(
                    "job_removed_from_queue_on_cancel",
                    job_id=job_id,
                    status="pending",
                )
            else:
                logger.info(
                    "job_not_in_queue_on_cancel",
                    job_id=job_id,
                    reason="may_have_been_picked_up_by_worker",
                )
                # Not a failure - job might have just been picked up by a worker
                # The Redis cancellation flag will handle it

        # Atomically update job status to cancelled in database
        # The SQL query only updates if status is 'pending' or 'running'
        # Returns None if the job is not in a cancellable state (race condition or already final)
        cancelled_job = await self.crawl_job_repo.cancel(
            job_id=job_id,
            cancelled_by=None,  # No user tracking yet (authorization not implemented)
            reason=request.reason,
        )

        # Handle case where atomic update returned None
        if not cancelled_job:
            # Re-fetch job to determine why the update failed
            current_job = await self.crawl_job_repo.get_by_id(job_id)

            if not current_job:
                # Job was deleted between our checks (unlikely but possible)
                logger.error("job_disappeared", job_id=job_id)
                await self.cancellation_flag.clear_cancellation(job_id)
                raise RuntimeError(f"Job with ID '{job_id}' no longer exists")

            # Idempotent: if job is already cancelled, treat as success
            if current_job.status == StatusEnum.CANCELLED:
                logger.info(
                    "job_already_cancelled_idempotent",
                    job_id=job_id,
                    cancelled_at=current_job.cancelled_at,
                )
                # Enforce data integrity: cancelled jobs must have cancelled_at timestamp
                assert current_job.cancelled_at is not None, (
                    "Data corruption: job is CANCELLED but cancelled_at is NULL"
                )

                return CancelJobResponse(
                    id=current_job.id,
                    status=CrawlJobStatus(
                        job_id=current_job.id, status=_safe_convert_status(current_job.status)
                    ),
                    message="Job is already cancelled",
                    cancelled_at=current_job.cancelled_at,
                )

            # Job is in a final state (completed or failed) - cannot cancel
            if current_job.status in (StatusEnum.COMPLETED, StatusEnum.FAILED):
                logger.warning(
                    "job_cannot_be_cancelled",
                    job_id=job_id,
                    status=current_job.status.value,
                )
                await self.cancellation_flag.clear_cancellation(job_id)
                raise ValueError(
                    f"Job is already {current_job.status.value} and cannot be cancelled"
                )

            # Unexpected state - should not happen
            logger.error(
                "unexpected_cancellation_failure",
                job_id=job_id,
                current_status=current_job.status.value,
            )
            await self.cancellation_flag.clear_cancellation(job_id)
            raise RuntimeError(
                f"Failed to cancel job - unexpected status: {current_job.status.value}"
            )

        logger.info(
            "job_cancelled",
            job_id=job_id,
            reason=request.reason,
            cancelled_at=cancelled_job.cancelled_at,
        )

        # Build response
        # Enforce contract: repository must set cancelled_at timestamp
        assert cancelled_job.cancelled_at is not None, (
            "Repository failed to set cancelled_at timestamp"
        )

        return CancelJobResponse(
            id=cancelled_job.id,
            status=CrawlJobStatus(
                job_id=cancelled_job.id, status=_safe_convert_status(cancelled_job.status)
            ),
            message="Job cancellation initiated",
            cancelled_at=cancelled_job.cancelled_at,
        )
