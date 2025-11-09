"""Crawl log request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from datetime import datetime

from crawler.api.generated import CrawlLogsResponse, LogLevelEnum
from crawler.api.v1.decorators import handle_service_errors
from crawler.api.v1.services import LogService
from crawler.core.logging import get_logger

logger = get_logger(__name__)


@handle_service_errors(operation="retrieving job logs")
async def get_job_logs_handler(
    job_id: str,
    log_service: LogService,
    log_level: LogLevelEnum | None = None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    search: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> CrawlLogsResponse:
    """Handle job log retrieval with HTTP error translation.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses via the decorator.

    Args:
        job_id: Job ID to retrieve logs for
        log_service: Injected log service
        log_level: Optional log level filter
        start_time: Optional start timestamp filter
        end_time: Optional end timestamp filter
        search: Optional text search in message
        limit: Number of logs per page
        offset: Offset for pagination

    Returns:
        Paginated log response

    Raises:
        HTTPException: If validation fails or operation fails
    """
    log_context = {
        "job_id": job_id,
        "log_level": log_level.value if log_level else None,
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat() if end_time else None,
        "search": search,
        "limit": limit,
        "offset": offset,
    }
    logger.info("get_job_logs_request", **log_context)

    # Delegate to service layer (error handling done by decorator)
    return await log_service.get_job_logs(
        job_id=job_id,
        log_level=log_level,
        start_time=start_time,
        end_time=end_time,
        search=search,
        limit=limit,
        offset=offset,
    )
