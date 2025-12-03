"""NATS JetStream queue service for distributed job processing.

Provides reliable message queuing for crawl jobs with:
- Durable streams for persistence
- Consumer acknowledgment for reliability
- Job cancellation via message deletion
- Dead letter queue for failed jobs
"""

import json
from typing import Any

import nats
from nats.aio.client import Client as NATSClient
from nats.js import JetStreamContext
from nats.js.api import (
    ConsumerConfig,
    DeliverPolicy,
    DiscardPolicy,
    RetentionPolicy,
    StreamConfig,
)
from nats.js.errors import NotFoundError

from config import Settings
from crawler.core.logging import get_logger

logger = get_logger(__name__)


class NATSQueueService:
    """NATS JetStream service for crawl job queuing.

    Manages job queue operations including:
    - Publishing jobs to the stream
    - Consuming jobs from the queue
    - Acknowledging processed jobs
    - Removing cancelled jobs from queue
    """

    def __init__(self, settings: Settings):
        """Initialize NATS queue service.

        Args:
            settings: Application settings with NATS configuration
        """
        self.settings = settings
        self.client: NATSClient | None = None
        self.js: JetStreamContext | None = None
        self.stream_name = settings.nats_stream_name
        self.consumer_name = settings.nats_consumer_name

    async def connect(self) -> None:
        """Connect to NATS server and initialize JetStream.

        Raises:
            RuntimeError: If connection or JetStream initialization fails
        """
        try:
            logger.info("connecting_to_nats", url=self.settings.nats_url)
            self.client = await nats.connect(self.settings.nats_url)
            self.js = self.client.jetstream()

            # Ensure stream exists
            await self._ensure_stream()
            # Ensure consumer exists
            await self._ensure_consumer()

            logger.info("nats_connected", stream=self.stream_name, consumer=self.consumer_name)
        except Exception as e:
            logger.error("nats_connection_failed", error=str(e))
            raise RuntimeError(f"Failed to connect to NATS: {e}") from e

    async def disconnect(self) -> None:
        """Disconnect from NATS server gracefully."""
        if self.client and not self.client.is_closed:
            try:
                logger.info("disconnecting_from_nats")
                await self.client.drain()
                await self.client.close()
                logger.info("nats_disconnected")
            except Exception as e:
                logger.error("nats_disconnect_error", error=str(e))

    async def _ensure_stream(self) -> None:
        """Ensure JetStream stream exists with proper configuration.

        Creates stream if it doesn't exist, updates if configuration differs.
        """
        if not self.js:
            raise RuntimeError("JetStream not initialized")

        stream_config = StreamConfig(
            name=self.stream_name,
            subjects=[f"{self.stream_name}.jobs"],
            retention=RetentionPolicy.WORK_QUEUE,  # Messages deleted after ack
            max_age=86400,  # 24 hours max retention
            max_msgs=100000,  # Max 100k pending jobs
            discard=DiscardPolicy.NEW,  # Reject new jobs when full (prevents silent loss)
            duplicate_window=300,  # 5 minutes deduplication window
        )

        try:
            # Try to get existing stream info
            await self.js.stream_info(self.stream_name)
            logger.info("nats_stream_exists", stream=self.stream_name)
            # Update stream config if needed
            await self.js.update_stream(stream_config)
            logger.info("nats_stream_updated", stream=self.stream_name)
        except Exception:
            # Stream doesn't exist, create it
            logger.info("creating_nats_stream", stream=self.stream_name)
            await self.js.add_stream(stream_config)
            logger.info("nats_stream_created", stream=self.stream_name)

    async def _ensure_consumer(self) -> None:
        """Ensure durable consumer exists for job processing.

        Creates consumer if it doesn't exist with proper configuration.
        """
        if not self.js:
            raise RuntimeError("JetStream not initialized")

        consumer_config = ConsumerConfig(
            durable_name=self.consumer_name,
            deliver_policy=DeliverPolicy.ALL,  # Deliver all available messages
            ack_wait=300,  # 5 minutes to process before redelivery
            max_deliver=3,  # Max 3 delivery attempts
            max_ack_pending=10,  # Max 10 unacked messages per consumer
        )

        try:
            # Try to get existing consumer info
            await self.js.consumer_info(self.stream_name, self.consumer_name)
            logger.info("nats_consumer_exists", consumer=self.consumer_name)
        except Exception:
            # Consumer doesn't exist, create it
            logger.info("creating_nats_consumer", consumer=self.consumer_name)
            await self.js.add_consumer(self.stream_name, consumer_config)
            logger.info("nats_consumer_created", consumer=self.consumer_name)

    async def publish_job(self, job_id: str, job_data: dict[str, Any]) -> bool:
        """Publish a job to the queue.

        Args:
            job_id: Unique job identifier
            job_data: Job payload (will be JSON serialized)

        Returns:
            True if published successfully, False otherwise

        Note:
            With DiscardPolicy.NEW, if the queue is full (max_msgs reached),
            the publish will fail with an error. This prevents silent job loss.
        """
        if not self.js:
            logger.error("nats_not_connected", operation="publish")
            return False

        try:
            subject = f"{self.stream_name}.jobs"
            payload = json.dumps({"job_id": job_id, **job_data})

            # Publish with message ID for deduplication
            ack = await self.js.publish(
                subject,
                payload.encode("utf-8"),
                headers={"Nats-Msg-Id": job_id},  # Deduplication based on job_id
            )

            logger.info(
                "job_published_to_queue",
                job_id=job_id,
                stream=ack.stream,
                sequence=ack.seq,
            )
            return True
        except Exception as e:
            # Check if this is a queue full error
            error_msg = str(e).lower()
            if "maximum messages" in error_msg or "stream store maximum" in error_msg:
                logger.error(
                    "queue_full_rejected_job",
                    job_id=job_id,
                    error=str(e),
                    action="scale_workers_or_increase_capacity",
                )
            else:
                logger.error("job_publish_failed", job_id=job_id, error=str(e))
            return False

    async def delete_job_from_queue(self, job_id: str) -> bool:
        """Remove a job from the queue (for cancellation).

        This is complex because NATS JetStream doesn't support direct message deletion
        by content. We need to:
        1. Get all pending messages
        2. Find messages with matching job_id
        3. Acknowledge them (removes from queue)

        Args:
            job_id: Job ID to remove from queue

        Returns:
            True if job was found and removed, False otherwise
        """
        if not self.js:
            logger.error("nats_not_connected", operation="delete")
            return False

        try:
            # Create a temporary pull subscription to search for the message
            psub = await self.js.pull_subscribe(
                subject=f"{self.stream_name}.jobs",
                durable=f"temp-cancel-{job_id[:8]}",
            )

            removed = False
            try:
                # Fetch pending messages (batch of 100)
                msgs = await psub.fetch(batch=100, timeout=1.0)

                for msg in msgs:
                    try:
                        # Parse message payload
                        data = json.loads(msg.data.decode("utf-8"))
                        msg_job_id = data.get("job_id")

                        if msg_job_id == job_id:
                            # Found the job - acknowledge to remove from queue
                            await msg.ack()
                            logger.info(
                                "job_removed_from_queue",
                                job_id=job_id,
                                sequence=msg.metadata.sequence.stream,
                            )
                            removed = True
                        else:
                            # Not our job - negative ack to requeue
                            await msg.nak()
                    except Exception as e:
                        logger.warning("failed_to_process_message", error=str(e))
                        await msg.nak()

            finally:
                # Clean up temporary subscription
                await psub.unsubscribe()
                # Delete the temporary consumer (may already be gone if unsubscribe cleaned it up)
                try:
                    await self.js.delete_consumer(
                        self.stream_name,
                        f"temp-cancel-{job_id[:8]}",
                    )
                except NotFoundError:
                    # Consumer already deleted or never existed - this is expected
                    pass
                except Exception as e:
                    # Log unexpected errors but don't fail the cancellation operation
                    logger.warning(
                        "failed_to_delete_temp_consumer",
                        consumer=f"temp-cancel-{job_id[:8]}",
                        error=str(e),
                        error_type=type(e).__name__,
                    )

            if removed:
                logger.info("job_cancelled_from_queue", job_id=job_id)
            else:
                logger.warning(
                    "job_not_found_in_queue",
                    job_id=job_id,
                    reason="may_have_already_started_or_not_yet_published",
                )

            return removed

        except Exception as e:
            logger.error("queue_deletion_failed", job_id=job_id, error=str(e))
            return False

    async def get_pending_job_count(self) -> int:
        """Get the number of pending jobs in the queue.

        Returns:
            Number of pending messages
        """
        if not self.js:
            logger.error("nats_not_connected", operation="get_count")
            return 0

        try:
            stream_info = await self.js.stream_info(self.stream_name)
            return int(stream_info.state.messages)
        except Exception as e:
            logger.error("failed_to_get_pending_count", error=str(e))
            return 0

    async def get_consumer_info(self) -> dict[str, Any] | None:
        """Get consumer status and metrics.

        Returns:
            Consumer info dict or None if error
        """
        if not self.js:
            logger.error("nats_not_connected", operation="get_consumer_info")
            return None

        try:
            consumer_info = await self.js.consumer_info(self.stream_name, self.consumer_name)
            return {
                "name": consumer_info.name,
                "num_pending": consumer_info.num_pending,
                "num_redelivered": consumer_info.num_redelivered,
                "num_waiting": consumer_info.num_waiting,
                "num_ack_pending": consumer_info.num_ack_pending,
                "num_delivered": consumer_info.delivered.consumer_seq,
            }
        except Exception as e:
            logger.error("failed_to_get_consumer_info", error=str(e))
            return None

    async def health_check(self) -> bool:
        """Check if NATS connection is healthy.

        Returns:
            True if connected and healthy, False otherwise
        """
        if not self.client or self.client.is_closed:
            return False

        try:
            # Try to get stream info as a health check
            if self.js:
                await self.js.stream_info(self.stream_name)
                return True
        except Exception as e:
            logger.warning("nats_health_check_failed", error=str(e))

        return False
