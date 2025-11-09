"""NATS-based log publisher for real-time log streaming.

Publishes crawl logs to NATS subjects for consumption by WebSocket endpoints.
This enables true real-time log streaming without database polling.
"""

from typing import TYPE_CHECKING

from nats.aio.client import Client as NATSClient

from crawler.api.websocket_models import WebSocketLogMessage
from crawler.core.logging import get_logger
from crawler.db.generated.models import CrawlLog

if TYPE_CHECKING:
    from crawler.services.redis_cache import LogBuffer

logger = get_logger(__name__)


class LogPublisher:
    """Publishes crawl logs to NATS for real-time WebSocket streaming.

    Architecture:
    - Logs are inserted into PostgreSQL (source of truth)
    - After insert, logs are published to NATS subject: logs.{job_id}
    - Logs are also buffered in Redis (max 1000) for reconnection support
    - WebSocket endpoints subscribe to these subjects for real-time updates
    - If NATS is unavailable, logs are still stored in DB (graceful degradation)

    Benefits:
    - True real-time streaming (<50ms latency)
    - Scalable (NATS handles fan-out to multiple subscribers)
    - No database polling overhead
    - Reconnection support via Redis buffer
    """

    def __init__(
        self, nats_client: NATSClient | None = None, log_buffer: "LogBuffer | None" = None
    ):
        """Initialize log publisher.

        Args:
            nats_client: NATS client for publishing. If None, publishing is disabled.
            log_buffer: Redis log buffer for reconnection. If None, buffering is disabled.
        """
        self.nats_client = nats_client
        self.log_buffer = log_buffer
        self._enabled = nats_client is not None and not nats_client.is_closed

    @property
    def is_enabled(self) -> bool:
        """Check if log publishing is enabled.

        Returns:
            True if NATS client is connected and publishing is enabled
        """
        return self._enabled and self.nats_client is not None and not self.nats_client.is_closed

    async def publish_log(self, log: CrawlLog) -> None:
        """Publish crawl log to NATS for real-time streaming and buffer in Redis.

        Publishes to subject: logs.{job_id}
        Message format: WebSocketLogMessage (JSON)
        Also buffers the log in Redis for reconnection support.

        Args:
            log: CrawlLog from database

        Note:
            If NATS is unavailable, this fails silently with a warning.
            Logs are still persisted in the database.
        """
        message = WebSocketLogMessage.from_crawl_log(log)
        message_dict = message.model_dump()

        # Buffer log in Redis for reconnection support
        if self.log_buffer:
            try:
                await self.log_buffer.add_log(
                    job_id=str(log.job_id), log_id=log.id, log_data=message_dict
                )
            except Exception as e:
                logger.warning(
                    "log_buffer_failed",
                    job_id=str(log.job_id),
                    log_id=log.id,
                    error=str(e),
                )

        # Guard: NATS not enabled
        if not self.is_enabled:
            return

        # Guard: NATS client not available
        if not self.nats_client:
            return

        try:
            subject = f"logs.{log.job_id}"

            # Publish to NATS
            await self.nats_client.publish(
                subject=subject,
                payload=message.model_dump_json().encode("utf-8"),
            )

            logger.debug(
                "log_published_to_nats",
                job_id=str(log.job_id),
                log_id=log.id,
                subject=subject,
            )

        except Exception as e:
            # Don't fail the operation if NATS publishing fails
            # Logs are still in the database and can be retrieved
            logger.warning(
                "log_publish_failed",
                job_id=str(log.job_id),
                log_id=log.id,
                error=str(e),
            )

    async def publish_logs_batch(self, logs: list[CrawlLog]) -> None:
        """Publish multiple logs in batch.

        More efficient than calling publish_log() multiple times.

        Args:
            logs: List of CrawlLog entries to publish
        """
        # Guard: NATS not enabled
        if not self.is_enabled:
            return

        # Guard: empty batch
        if not logs:
            return

        for log in logs:
            await self.publish_log(log)

    def disable(self) -> None:
        """Disable log publishing.

        Useful for testing or when NATS is intentionally unavailable.
        """
        self._enabled = False
        logger.info("log_publishing_disabled")

    def enable(self) -> None:
        """Enable log publishing (if NATS client is available)."""
        if self.nats_client and not self.nats_client.is_closed:
            self._enabled = True
            logger.info("log_publishing_enabled")
