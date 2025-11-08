"""WebSocket endpoints for real-time features."""

import asyncio
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from crawler.api.websocket_models import WebSocketLogMessage
from crawler.core.dependencies import (
    LogPublisherDep,
    NATSQueueDep,
    WebSocketTokenServiceDep,
    get_database,
)
from crawler.core.logging import get_logger
from crawler.db.repositories import CrawlLogRepository

logger = get_logger(__name__)

router = APIRouter(prefix="/ws/v1")


@router.websocket("/jobs/{job_id}/logs")
async def stream_job_logs(
    websocket: WebSocket,
    job_id: str,
    token: str,
    ws_token_service: WebSocketTokenServiceDep,
    nats_queue_service: NATSQueueDep,
    log_publisher: LogPublisherDep,
) -> None:
    """WebSocket endpoint for real-time job log streaming via NATS.

    This endpoint provides true real-time log streaming for crawl jobs using
    NATS pub/sub. Logs are published to NATS after database insertion and
    immediately streamed to WebSocket clients (<50ms latency).

    Connection flow:
    1. Client obtains token from POST /api/v1/jobs/{job_id}/ws-token
    2. Client connects to /ws/v1/jobs/{job_id}/logs?token={token}
    3. Server validates token (single-use, 10-minute TTL)
    4. Server sends initial logs from database (last 50)
    5. Server subscribes to NATS subject: logs.{job_id}
    6. New logs are streamed in real-time via NATS (<50ms latency)
    7. Falls back to database polling if NATS unavailable (2s latency)

    Message format: See WebSocketLogMessage model for complete schema.

    Args:
        websocket: WebSocket connection
        job_id: Job ID to stream logs for
        token: Authentication token from token endpoint
        ws_token_service: WebSocket token service from dependency
        nats_queue_service: NATS queue service (provides NATS client)
        log_publisher: Log publisher (checks if NATS enabled)
    """
    # Validate token before accepting connection
    is_valid = await ws_token_service.validate_and_consume_token(token, job_id)

    # Guard: invalid token
    if not is_valid:
        await websocket.close(
            code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token"
        )
        logger.warning("ws_connection_rejected", job_id=job_id, reason="invalid_token")
        return

    # Accept connection
    await websocket.accept()
    logger.info("ws_connection_accepted", job_id=job_id)

    # Get database session (manual handling for WebSocket)
    async for db_session in get_database():
        try:
            # Get repository
            conn = await db_session.connection()
            log_repo = CrawlLogRepository(conn, log_publisher=log_publisher)

            # Send initial logs (last 50)
            last_timestamp = await _send_initial_logs(websocket, log_repo, job_id)

            # Choose streaming strategy based on NATS availability
            use_nats = log_publisher.is_enabled and nats_queue_service.client
            if use_nats:
                logger.info("ws_using_nats_streaming", job_id=job_id)
                await _stream_logs_via_nats(
                    websocket=websocket,
                    job_id=job_id,
                    nats_client=nats_queue_service.client,
                )
            else:
                logger.warning(
                    "ws_using_polling_fallback",
                    job_id=job_id,
                    reason="nats_unavailable",
                )
                await _stream_logs_via_polling(
                    websocket=websocket,
                    log_repo=log_repo,
                    job_id=job_id,
                    last_timestamp=last_timestamp,
                )

        except WebSocketDisconnect:
            logger.info("ws_connection_closed", job_id=job_id)
        except Exception as e:
            logger.error("ws_connection_error", job_id=job_id, error=str(e))
        finally:
            # Cleanup
            logger.info("ws_connection_terminated", job_id=job_id)

        # Exit the database session loop after first iteration
        break


async def _send_initial_logs(
    websocket: WebSocket,
    log_repo: CrawlLogRepository,
    job_id: str,
) -> datetime:
    """Send initial logs from database (last 50).

    Args:
        websocket: WebSocket connection
        log_repo: Log repository
        job_id: Job ID

    Returns:
        Timestamp of the last sent log (for polling fallback)
    """
    last_timestamp = datetime.now(UTC)

    try:
        initial_logs = await log_repo.list_by_job(job_id=job_id, limit=50, offset=0)
        for log in reversed(initial_logs):  # Reverse to send oldest first
            message = WebSocketLogMessage.from_crawl_log(log)
            await websocket.send_json(message.model_dump())
            last_timestamp = log.created_at
        logger.info("ws_initial_logs_sent", job_id=job_id, count=len(initial_logs))
    except Exception as e:
        logger.error("ws_initial_logs_error", job_id=job_id, error=str(e))

    return last_timestamp


async def _stream_logs_via_nats(
    websocket: WebSocket,
    job_id: str,
    nats_client: Any,
) -> None:
    """Stream logs via NATS subscription with batching (100ms window).

    Batches log messages every 100ms to handle high log volume efficiently.
    This reduces WebSocket message overhead while maintaining low latency.

    Args:
        websocket: WebSocket connection
        job_id: Job ID
        nats_client: NATS client from queue service
    """
    subject = f"logs.{job_id}"
    subscription = None
    message_buffer: list[str] = []
    loop = asyncio.get_running_loop()
    last_flush_time = loop.time()
    batch_interval = 0.1  # 100ms batching window

    async def flush_buffer() -> None:
        """Flush buffered messages to WebSocket."""
        nonlocal message_buffer, last_flush_time
        if not message_buffer:
            return

        try:
            # Send all buffered messages as a JSON array
            await websocket.send_json(message_buffer)
            logger.debug(
                "ws_batch_sent",
                job_id=job_id,
                batch_size=len(message_buffer),
            )
            message_buffer = []
            last_flush_time = loop.time()
        except Exception as e:
            logger.error("ws_batch_send_error", job_id=job_id, error=str(e))
            raise

    try:
        # Subscribe to NATS subject for this job
        subscription = await nats_client.subscribe(subject)
        logger.info("ws_nats_subscribed", job_id=job_id, subject=subject)

        # Stream messages from NATS to WebSocket with batching
        while True:
            try:
                # Calculate time until next flush
                current_time = loop.time()
                time_since_flush = current_time - last_flush_time
                timeout = max(0.01, batch_interval - time_since_flush)

                # Wait for message with dynamic timeout
                msg = await asyncio.wait_for(subscription.next_msg(), timeout=timeout)

                # Add message to buffer (already JSON encoded string)
                message_buffer.append(msg.data.decode("utf-8"))

                # Flush if batch interval reached
                if (loop.time() - last_flush_time) >= batch_interval:
                    await flush_buffer()

            except TimeoutError:
                # Flush any pending messages on timeout
                await flush_buffer()
                continue
            except WebSocketDisconnect:
                logger.info("ws_client_disconnected_nats", job_id=job_id)
                break

    except Exception as e:
        logger.error("ws_nats_streaming_error", job_id=job_id, error=str(e))
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="NATS error")
    finally:
        # Flush any remaining messages
        try:
            await flush_buffer()
        except Exception:
            pass  # WebSocket already closed

        # Cleanup NATS subscription
        if subscription:
            try:
                await subscription.unsubscribe()
                logger.info("ws_nats_unsubscribed", job_id=job_id)
            except Exception as e:
                logger.error("ws_nats_unsubscribe_error", job_id=job_id, error=str(e))


async def _stream_logs_via_polling(
    websocket: WebSocket,
    log_repo: CrawlLogRepository,
    job_id: str,
    last_timestamp: datetime,
) -> None:
    """Stream logs via database polling (fallback, 2s latency).

    Used when NATS is unavailable. Polls database every 2 seconds.

    Args:
        websocket: WebSocket connection
        log_repo: Log repository
        job_id: Job ID
        last_timestamp: Last timestamp seen (to avoid duplicates)
    """
    while True:
        try:
            # Poll for new logs every 2 seconds
            await asyncio.sleep(2)

            # Get new logs since last timestamp
            new_logs = await log_repo.stream_logs_by_job(
                job_id=job_id,
                after_timestamp=last_timestamp,
                limit=100,
            )

            # Send new logs
            for log in new_logs:
                message = WebSocketLogMessage.from_crawl_log(log)
                await websocket.send_json(message.model_dump())
                last_timestamp = log.created_at

        except WebSocketDisconnect:
            logger.info("ws_client_disconnected_polling", job_id=job_id)
            break
        except Exception as e:
            logger.error("ws_polling_error", job_id=job_id, error=str(e))
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Polling error")
            break
