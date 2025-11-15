"""DLQ request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from crawler.api.generated import (
    DLQEntriesResponse,
    DLQEntryResponse,
    DLQRetryResponse,
    DLQStatsResponse,
    ErrorCategoryEnum,
    ResolveDLQRequest,
)
from crawler.api.v1.decorators import handle_service_errors
from crawler.api.v1.services import DLQService
from crawler.core.logging import get_logger

logger = get_logger(__name__)


@handle_service_errors(operation="listing DLQ entries")
async def list_dlq_entries_handler(
    dlq_service: DLQService,
    error_category: ErrorCategoryEnum | None = None,
    website_id: str | None = None,
    unresolved_only: bool | None = None,
    limit: int = 100,
    offset: int = 0,
) -> DLQEntriesResponse:
    """Handle DLQ entry listing with HTTP error translation.

    Args:
        dlq_service: Injected DLQ service
        error_category: Optional filter by error category
        website_id: Optional filter by website
        unresolved_only: Optional filter by resolved status
        limit: Number of entries per page
        offset: Offset for pagination

    Returns:
        Paginated DLQ entries response

    Raises:
        HTTPException: If validation fails or operation fails
    """
    log_context = {
        "error_category": error_category.value if error_category else None,
        "website_id": website_id,
        "unresolved_only": unresolved_only,
        "limit": limit,
        "offset": offset,
    }
    logger.info("list_dlq_entries_request", **log_context)

    # Delegate to service layer (error handling done by decorator)
    return await dlq_service.list_entries(
        error_category=error_category,
        website_id=website_id,
        unresolved_only=unresolved_only,
        limit=limit,
        offset=offset,
    )


@handle_service_errors(operation="retrieving DLQ entry")
async def get_dlq_entry_handler(
    dlq_id: int,
    dlq_service: DLQService,
) -> DLQEntryResponse:
    """Handle DLQ entry retrieval with HTTP error translation.

    Args:
        dlq_id: DLQ entry ID
        dlq_service: Injected DLQ service

    Returns:
        DLQ entry response

    Raises:
        HTTPException: If entry not found or operation fails
    """
    logger.info("get_dlq_entry_request", dlq_id=dlq_id)
    return await dlq_service.get_entry(dlq_id=dlq_id)


@handle_service_errors(operation="retrying DLQ entry")
async def retry_dlq_entry_handler(
    dlq_id: int,
    dlq_service: DLQService,
) -> DLQRetryResponse:
    """Handle DLQ entry manual retry with HTTP error translation.

    Args:
        dlq_id: DLQ entry ID to retry
        dlq_service: Injected DLQ service

    Returns:
        Retry response with new job ID

    Raises:
        HTTPException: If entry not found, already resolved, or retry fails
    """
    from fastapi import HTTPException, status

    logger.info("retry_dlq_entry_request", dlq_id=dlq_id)

    # Guard: Check if entry exists (return 404 per OpenAPI spec)
    entry = await dlq_service.dlq_repo.get_by_id(dlq_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DLQ entry with ID {dlq_id} not found",
        )

    # Entry exists, delegate to service (decorator handles business logic errors)
    return await dlq_service.retry_entry(dlq_id=dlq_id)


@handle_service_errors(operation="resolving DLQ entry")
async def resolve_dlq_entry_handler(
    dlq_id: int,
    dlq_service: DLQService,
    request: ResolveDLQRequest | None = None,
) -> DLQEntryResponse:
    """Handle DLQ entry resolution with HTTP error translation.

    Args:
        dlq_id: DLQ entry ID to resolve
        dlq_service: Injected DLQ service
        request: Optional resolution request with notes

    Returns:
        Updated DLQ entry response

    Raises:
        HTTPException: If entry not found, already resolved, or resolution fails
    """
    from fastapi import HTTPException, status

    resolution_notes = request.resolution_notes if request else None
    logger.info(
        "resolve_dlq_entry_request",
        dlq_id=dlq_id,
        has_notes=resolution_notes is not None,
    )

    # Guard: Check if entry exists (return 404 per OpenAPI spec)
    entry = await dlq_service.dlq_repo.get_by_id(dlq_id)
    if not entry:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"DLQ entry with ID {dlq_id} not found",
        )

    # Entry exists, delegate to service (decorator handles business logic errors)
    return await dlq_service.resolve_entry(
        dlq_id=dlq_id,
        resolution_notes=resolution_notes,
    )


@handle_service_errors(operation="retrieving DLQ statistics")
async def get_dlq_stats_handler(
    dlq_service: DLQService,
) -> DLQStatsResponse:
    """Handle DLQ statistics retrieval with HTTP error translation.

    Args:
        dlq_service: Injected DLQ service

    Returns:
        DLQ statistics response

    Raises:
        HTTPException: If stats retrieval fails
    """
    logger.info("get_dlq_stats_request")

    # Delegate to service layer (error handling done by decorator)
    return await dlq_service.get_stats()
