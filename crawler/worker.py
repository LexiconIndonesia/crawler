"""NATS queue worker for processing crawl jobs.

This worker:
1. Connects to NATS JetStream
2. Subscribes to the job queue
3. Fetches job details from database
4. Executes the crawl job
5. Updates job status
6. Acknowledges or rejects the message
"""

import asyncio
import json
import signal
from typing import Any

from nats.js.api import AckPolicy, ConsumerConfig

from config import Settings, get_settings
from crawler.core.logging import get_logger, setup_logging
from crawler.db.generated.models import StatusEnum
from crawler.db.repositories import CrawlJobRepository, WebsiteRepository
from crawler.db.session import get_db
from crawler.services.nats_queue import NATSQueueService
from crawler.services.redis_cache import JobCancellationFlag, URLDeduplicationCache
from crawler.services.step_orchestrator import StepOrchestrator

logger = get_logger(__name__)

# Global shutdown flag
_shutdown = False


def signal_handler(signum: int, frame: Any) -> None:
    """Handle shutdown signals gracefully."""
    global _shutdown
    logger.info("shutdown_signal_received", signal=signum)
    _shutdown = True


class CrawlJobWorker:
    """Worker that processes crawl jobs from NATS queue.

    Uses dependency injection for testability and clean architecture.
    """

    def __init__(
        self,
        nats_queue: NATSQueueService,
        cancellation_flag: JobCancellationFlag,
        dedup_cache: URLDeduplicationCache,
        settings: Settings,
    ):
        """Initialize worker with injected dependencies.

        Args:
            nats_queue: NATS queue service for consuming messages
            cancellation_flag: Job cancellation flag service
            dedup_cache: URL deduplication cache service
            settings: Application settings
        """
        self.nats_queue = nats_queue
        self.cancellation_flag = cancellation_flag
        self.dedup_cache = dedup_cache
        self.settings = settings
        self.processing = False

    async def setup(self) -> None:
        """Setup worker dependencies and connections."""
        logger.info("worker_setup_starting")

        # Connect to NATS (if not already connected)
        if not await self.nats_queue.health_check():
            await self.nats_queue.connect()

        logger.info("worker_setup_complete")

    async def teardown(self) -> None:
        """Cleanup worker resources."""
        logger.info("worker_teardown_starting")

        if self.nats_queue:
            await self.nats_queue.disconnect()

        logger.info("worker_teardown_complete")

    async def _load_workflow_config(
        self, job: Any, conn: Any
    ) -> tuple[list[dict[str, Any]], str, dict[str, Any]] | None:
        """Load workflow configuration from job (inline or template-based).

        Args:
            job: CrawlJob model instance
            conn: Database connection

        Returns:
            Tuple of (steps list, base_url, global_config) or None if invalid
        """
        try:
            # Case 1: Inline configuration (no website template)
            if job.inline_config:
                logger.info("loading_inline_config", job_id=str(job.id))

                # Parse inline config
                if not isinstance(job.inline_config, dict):
                    logger.error("invalid_inline_config_type", job_id=str(job.id))
                    return None

                steps = job.inline_config.get("steps", [])
                if not steps or not isinstance(steps, list):
                    logger.error("missing_or_invalid_steps", job_id=str(job.id))
                    return None

                # Convert Pydantic models to dicts for orchestrator
                steps_dicts = [
                    step.model_dump() if hasattr(step, "model_dump") else step for step in steps
                ]

                # Use seed_url as base_url for inline jobs
                base_url = str(job.seed_url)
                global_config = job.inline_config.get("config", {})
                return (steps_dicts, base_url, global_config)

            # Case 2: Template-based configuration (website_id)
            elif job.website_id:
                logger.info(
                    "loading_website_template", job_id=str(job.id), website_id=str(job.website_id)
                )

                # Load website from database
                website_repo = WebsiteRepository(conn)
                website = await website_repo.get_by_id(job.website_id)

                if not website:
                    logger.error("website_not_found", website_id=str(job.website_id))
                    return None

                # Parse website config
                if not website.config or not isinstance(website.config, dict):
                    logger.error("invalid_website_config", website_id=str(job.website_id))
                    return None

                steps = website.config.get("steps", [])
                if not steps or not isinstance(steps, list):
                    logger.error("missing_steps_in_website", website_id=str(job.website_id))
                    return None

                # Convert Pydantic models to dicts for orchestrator
                steps_dicts = [
                    step.model_dump() if hasattr(step, "model_dump") else step for step in steps
                ]

                # Get base_url from website or use seed_url
                base_url = website.base_url if hasattr(website, "base_url") else str(job.seed_url)
                global_config = website.config.get("config", {})
                return (steps_dicts, base_url, global_config)

            else:
                logger.error("job_has_no_config", job_id=str(job.id))
                return None

        except Exception as e:
            logger.error("config_loading_failed", job_id=str(job.id), error=str(e), exc_info=True)
            return None

    async def _process_job_with_connection(
        self, job_id: str, job_data: dict[str, Any], conn: Any
    ) -> bool:
        """Process job using the provided database connection.

        Args:
            job_id: Job UUID
            job_data: Job metadata from queue message
            conn: Database connection

        Returns:
            True if job processed successfully, False if it should be requeued
        """
        job_repo = CrawlJobRepository(conn)

        # Fetch full job details from database
        job = await job_repo.get_by_id(job_id)

        # Guard: job not found
        if not job:
            logger.error("job_not_found_in_db", job_id=job_id)
            # Acknowledge to remove from queue - job doesn't exist
            return True

        # Guard: job already completed or cancelled
        if job.status.value in ("completed", "cancelled", "failed"):
            logger.info(
                "job_already_finished",
                job_id=job_id,
                status=job.status.value,
            )
            # Acknowledge to remove from queue
            return True

        # Update job status to running
        await job_repo.update_status(
            job_id=job_id,
            status=StatusEnum.RUNNING,
            started_at=None,  # SQL will set to CURRENT_TIMESTAMP
            completed_at=None,
            error_message=None,
        )

        logger.info("job_status_updated_to_running", job_id=job_id)

        # Load workflow configuration (inline or from website template)
        workflow_config = await self._load_workflow_config(job, conn)

        # Guard: invalid configuration
        if not workflow_config:
            logger.error("invalid_job_configuration", job_id=job_id)
            await job_repo.update_status(
                job_id=job_id,
                status=StatusEnum.FAILED,
                started_at=None,
                completed_at=None,
                error_message="Invalid job configuration - missing or malformed steps",
            )
            return True

        steps, base_url, global_config = workflow_config

        # Get website_id from job (inline jobs may not have website_id)
        website_id = str(job.website_id) if job.website_id else None

        try:
            # Create step orchestrator for multi-step workflow execution
            logger.info(
                "starting_workflow",
                job_id=job_id,
                total_steps=len(steps),
                base_url=base_url,
            )

            orchestrator = StepOrchestrator(
                job_id=job_id,
                website_id=website_id or job_id,  # Use job_id if no website_id
                base_url=base_url,
                steps=steps,
                global_config=global_config,
            )

            # Execute workflow
            context = await orchestrator.execute_workflow()

            logger.info(
                "workflow_completed",
                job_id=job_id,
                successful_steps=len(context.get_successful_steps()),
                failed_steps=len(context.get_failed_steps()),
                total_steps=len(steps),
            )

            # Update job status based on workflow execution
            failed_steps = context.get_failed_steps()
            if not failed_steps:
                # All steps succeeded
                await job_repo.update_status(
                    job_id=job_id,
                    status=StatusEnum.COMPLETED,
                    started_at=None,
                    completed_at=None,
                    error_message=None,
                )
                logger.info("job_completed_successfully", job_id=job_id)
                return True
            else:
                # Some steps failed
                error_msg = f"Workflow failed. Failed steps: {', '.join(failed_steps)}"
                await job_repo.update_status(
                    job_id=job_id,
                    status=StatusEnum.FAILED,
                    started_at=None,
                    completed_at=None,
                    error_message=error_msg[:1000],  # Limit error message length
                )
                logger.warning(
                    "job_failed",
                    job_id=job_id,
                    failed_steps=failed_steps,
                )
                return True

        except ValueError as e:
            # Dependency validation or configuration error
            error_msg = f"Workflow configuration error: {e}"
            await job_repo.update_status(
                job_id=job_id,
                status=StatusEnum.FAILED,
                started_at=None,
                completed_at=None,
                error_message=error_msg[:1000],
            )
            logger.error("workflow_validation_error", job_id=job_id, error=str(e))
            return True

        except Exception as e:
            # Unexpected error
            error_msg = f"Workflow execution error: {e}"
            await job_repo.update_status(
                job_id=job_id,
                status=StatusEnum.FAILED,
                started_at=None,
                completed_at=None,
                error_message=error_msg[:1000],
            )
            logger.error("workflow_execution_error", job_id=job_id, error=str(e), exc_info=True)
            return True

    async def process_job(self, job_id: str, job_data: dict[str, Any], conn: Any = None) -> bool:
        """Process a single crawl job.

        Args:
            job_id: Job UUID
            job_data: Job metadata from queue message
            conn: Optional database connection (for testing)

        Returns:
            True if job processed successfully, False if it should be requeued
        """
        logger.info("processing_job", job_id=job_id, job_data=job_data)

        # Guard: check if job is cancelled before starting
        if self.cancellation_flag and await self.cancellation_flag.is_cancelled(job_id):
            logger.info("job_cancelled_before_start", job_id=job_id)
            # Job is cancelled - acknowledge to remove from queue
            return True

        try:
            # Use provided connection or get new one
            if conn is not None:
                # Test mode - use provided connection
                return await self._process_job_with_connection(job_id, job_data, conn)
            else:
                # Production mode - get connection from pool
                async for db_session in get_db():
                    conn = await db_session.connection()
                    return await self._process_job_with_connection(job_id, job_data, conn)
                # Edge case: no database session available
                logger.error("no_database_session_available", job_id=job_id)
                return False

        except Exception as e:
            logger.error("job_processing_failed", job_id=job_id, error=str(e), exc_info=True)
            # Return False to trigger negative acknowledgment and requeue
            return False

    async def run(self) -> None:
        """Run the worker main loop."""
        global _shutdown

        logger.info("worker_starting")

        try:
            await self.setup()

            if not self.nats_queue or not self.nats_queue.js:
                logger.error("nats_not_initialized")
                return

            # Create pull subscription
            psub = await self.nats_queue.js.pull_subscribe(
                subject=f"{self.settings.nats_stream_name}.jobs",
                durable=self.settings.nats_consumer_name,
                config=ConsumerConfig(ack_policy=AckPolicy.EXPLICIT),
            )

            logger.info("worker_subscribed_to_queue", consumer=self.settings.nats_consumer_name)

            # Main processing loop
            while not _shutdown:
                try:
                    # Fetch messages in batches
                    msgs = await psub.fetch(batch=1, timeout=5.0)

                    for msg in msgs:
                        # Guard: check shutdown flag
                        if _shutdown:
                            logger.info("shutdown_requested_stopping_processing")
                            # Negative ack to requeue for another worker
                            await msg.nak()
                            break

                        try:
                            # Parse message
                            data = json.loads(msg.data.decode("utf-8"))
                            job_id = data.get("job_id")

                            if not job_id:
                                logger.warning("message_missing_job_id", data=data)
                                # Acknowledge bad message to remove from queue
                                await msg.ack()
                                continue

                            # Process the job
                            self.processing = True
                            success = await self.process_job(job_id, data)
                            self.processing = False

                            if success:
                                # Job processed successfully - acknowledge
                                await msg.ack()
                                logger.info("message_acknowledged", job_id=job_id)
                            else:
                                # Job failed - negative acknowledge for requeue
                                await msg.nak()
                                logger.warning("message_rejected_for_requeue", job_id=job_id)

                        except Exception as e:
                            logger.error("message_processing_error", error=str(e), exc_info=True)
                            # Negative ack on error to requeue
                            await msg.nak()

                except TimeoutError:
                    # No messages available - this is normal
                    logger.debug("no_messages_available")
                    continue
                except Exception as e:
                    logger.error("fetch_error", error=str(e), exc_info=True)
                    await asyncio.sleep(5)  # Wait before retrying

            logger.info("worker_main_loop_exited")

        except Exception as e:
            logger.error("worker_fatal_error", error=str(e), exc_info=True)
        finally:
            await self.teardown()


async def main() -> None:
    """Main entry point for the worker."""
    # Setup logging
    setup_logging()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Get settings
    settings = get_settings()

    # Setup dependencies
    logger.info("initializing_worker_dependencies")

    # Setup Redis client
    import redis.asyncio as redis

    redis_client = await redis.from_url(settings.redis_url)

    # Create services
    nats_queue = NATSQueueService(settings)
    cancellation_flag = JobCancellationFlag(redis_client, settings)
    dedup_cache = URLDeduplicationCache(redis_client, settings)

    # Create and run worker with dependency injection
    worker = CrawlJobWorker(
        nats_queue=nats_queue,
        cancellation_flag=cancellation_flag,
        dedup_cache=dedup_cache,
        settings=settings,
    )

    try:
        await worker.run()
    finally:
        # Cleanup
        await redis_client.aclose()  # type: ignore[attr-defined]


if __name__ == "__main__":
    asyncio.run(main())
