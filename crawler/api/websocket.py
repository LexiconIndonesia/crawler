"""WebSocket endpoints for real-time features."""

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from crawler.core.dependencies import WebSocketTokenServiceDep, get_database
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
) -> None:
    """WebSocket endpoint for real-time job log streaming.

    This endpoint provides real-time log streaming for a crawl job.
    Clients must provide a valid short-lived token obtained from
    POST /api/v1/jobs/{job_id}/ws-token.

    Connection flow:
    1. Client obtains token from POST /api/v1/jobs/{job_id}/ws-token
    2. Client connects to /ws/v1/jobs/{job_id}/logs?token={token}
    3. Server validates token (single-use, 10-minute TTL)
    4. Server sends logs in real-time as JSON messages
    5. Server polls database every 2 seconds for new logs

    Message format:
    {
        "id": 12345,
        "job_id": "uuid",
        "log_level": "INFO",
        "message": "Log message",
        "step_name": "step_name",
        "context": {...},
        "trace_id": "uuid",
        "created_at": "2025-01-01T00:00:00Z"
    }

    Args:
        websocket: WebSocket connection
        job_id: Job ID to stream logs for
        token: Authentication token from token endpoint
        ws_token_service: WebSocket token service from dependency
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
            # Track last timestamp to avoid sending duplicate logs
            last_timestamp = datetime.now(UTC)

            # Get repository
            conn = await db_session.connection()
            log_repo = CrawlLogRepository(conn)

            # Send initial logs (last 50)
            try:
                initial_logs = await log_repo.list_by_job(job_id=job_id, limit=50, offset=0)
                for log in reversed(initial_logs):  # Reverse to send oldest first
                    await websocket.send_json(
                        {
                            "id": log.id,
                            "job_id": str(log.job_id),
                            "website_id": str(log.website_id),
                            "log_level": log.log_level.value,
                            "message": log.message,
                            "step_name": log.step_name,
                            "context": log.context,
                            "trace_id": str(log.trace_id) if log.trace_id else None,
                            "created_at": log.created_at.isoformat(),
                        }
                    )
                    last_timestamp = log.created_at
            except Exception as e:
                logger.error("ws_initial_logs_error", job_id=job_id, error=str(e))

            # Streaming loop
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
                        await websocket.send_json(
                            {
                                "id": log.id,
                                "job_id": str(log.job_id),
                                "website_id": str(log.website_id),
                                "log_level": log.log_level.value,
                                "message": log.message,
                                "step_name": log.step_name,
                                "context": log.context,
                                "trace_id": str(log.trace_id) if log.trace_id else None,
                                "created_at": log.created_at.isoformat(),
                            }
                        )
                        last_timestamp = log.created_at

                except WebSocketDisconnect:
                    logger.info("ws_client_disconnected", job_id=job_id)
                    break
                except Exception as e:
                    logger.error("ws_streaming_error", job_id=job_id, error=str(e))
                    await websocket.close(
                        code=status.WS_1011_INTERNAL_ERROR, reason="Internal error"
                    )
                    break

        except WebSocketDisconnect:
            logger.info("ws_connection_closed", job_id=job_id)
        except Exception as e:
            logger.error("ws_connection_error", job_id=job_id, error=str(e))
        finally:
            # Cleanup
            logger.info("ws_connection_terminated", job_id=job_id)

        # Exit the database session loop after first iteration
        break
