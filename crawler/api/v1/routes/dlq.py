"""Dead Letter Queue management routes for API v1."""

from fastapi import APIRouter, Body, Path, Query, status

from crawler.api.generated import (
    DLQEntriesResponse,
    DLQEntryResponse,
    DLQRetryResponse,
    DLQStatsResponse,
    ErrorCategoryEnum,
    ErrorResponse,
    ResolveDLQRequest,
)
from crawler.api.v1.dependencies import DLQServiceDep
from crawler.api.v1.handlers import (
    get_dlq_entry_handler,
    get_dlq_stats_handler,
    list_dlq_entries_handler,
    resolve_dlq_entry_handler,
    retry_dlq_entry_handler,
)

router = APIRouter()


@router.get(
    "/entries",
    response_model=DLQEntriesResponse,
    status_code=status.HTTP_200_OK,
    summary="List dead letter queue entries",
    operation_id="listDLQEntries",
    description="""
    List permanently failed jobs in the Dead Letter Queue with filtering and pagination.

    The DLQ contains jobs that have:
    - Exceeded maximum retry attempts
    - Failed with non-retryable errors (404, 401, validation errors)

    **Filtering options:**
    - `error_category`: Filter by error type
    - `website_id`: Filter by website
    - `unresolved_only`: Show only unresolved entries

    **Pagination:**
    - Use `limit` and `offset` for pagination
    - Default limit is 100, max is 500
    """,
    responses={
        200: {"description": "DLQ entries retrieved successfully"},
        400: {
            "description": "Invalid query parameters",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def list_dlq_entries(
    dlq_service: DLQServiceDep,
    error_category: ErrorCategoryEnum | None = Query(None, description="Filter by error category"),
    website_id: str | None = Query(None, description="Filter by website ID"),
    unresolved_only: bool | None = Query(
        None,
        description="Show only unresolved entries (true) or only resolved (false), or all (omit)",
    ),
    limit: int = Query(100, ge=1, le=500, description="Number of entries to return (max 500)"),
    offset: int = Query(0, ge=0, description="Number of entries to skip for pagination"),
) -> DLQEntriesResponse:
    """List DLQ entries with filtering and pagination.

    Args:
        dlq_service: Injected DLQ service
        error_category: Optional filter by error category
        website_id: Optional filter by website
        unresolved_only: Optional filter by resolved status
        limit: Number of entries per page (1-500)
        offset: Number of entries to skip

    Returns:
        Paginated DLQ entries response

    Raises:
        HTTPException 400: If validation fails
        HTTPException 500: If database operation fails
    """
    return await list_dlq_entries_handler(
        dlq_service, error_category, website_id, unresolved_only, limit, offset
    )


@router.get(
    "/entries/{dlq_id}",
    response_model=DLQEntryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get DLQ entry details",
    operation_id="getDLQEntry",
    description="""
    Retrieve detailed information about a specific Dead Letter Queue entry.

    Includes:
    - Job metadata (URL, website, type, priority)
    - Error details (category, message, stack trace, HTTP status)
    - Retry history (total attempts, timing)
    - Resolution status
    """,
    responses={
        200: {"description": "DLQ entry retrieved successfully"},
        404: {
            "description": "DLQ entry not found",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def get_dlq_entry(
    dlq_service: DLQServiceDep,
    dlq_id: int = Path(..., description="DLQ entry ID", gt=0),
) -> DLQEntryResponse:
    """Get a specific DLQ entry by ID.

    Args:
        dlq_service: Injected DLQ service
        dlq_id: DLQ entry ID

    Returns:
        DLQ entry response

    Raises:
        HTTPException 404: If entry not found
        HTTPException 500: If database operation fails
    """
    return await get_dlq_entry_handler(dlq_id, dlq_service)


@router.post(
    "/entries/{dlq_id}/retry",
    response_model=DLQRetryResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually retry a DLQ entry",
    operation_id="retryDLQEntry",
    description="""
    Attempt to manually retry a permanently failed job from the DLQ.

    This endpoint:
    1. Creates a new crawl job with the same configuration
    2. Marks the DLQ entry as retry attempted
    3. Returns the new job ID for tracking

    **Note:** The original DLQ entry is kept for audit purposes.
    The retry attempt status is tracked separately.
    """,
    responses={
        200: {"description": "Retry initiated successfully"},
        404: {
            "description": "DLQ entry not found",
            "model": ErrorResponse,
        },
        409: {
            "description": "Entry already resolved or retry in progress",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def retry_dlq_entry(
    dlq_service: DLQServiceDep,
    dlq_id: int = Path(..., description="DLQ entry ID to retry", gt=0),
) -> DLQRetryResponse:
    """Manually retry a DLQ entry.

    Args:
        dlq_service: Injected DLQ service
        dlq_id: DLQ entry ID to retry

    Returns:
        Retry response with new job ID

    Raises:
        HTTPException 404: If entry not found
        HTTPException 409: If entry already resolved
        HTTPException 500: If retry fails
    """
    return await retry_dlq_entry_handler(dlq_id, dlq_service)


@router.post(
    "/entries/{dlq_id}/resolve",
    response_model=DLQEntryResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark DLQ entry as resolved",
    operation_id="resolveDLQEntry",
    description="""
    Mark a DLQ entry as resolved without retrying.

    Use this when:
    - The issue has been fixed manually
    - The failure is expected and should be ignored
    - The job is no longer relevant

    Resolution notes are optional but recommended for audit purposes.
    """,
    responses={
        200: {"description": "DLQ entry resolved successfully"},
        404: {
            "description": "DLQ entry not found",
            "model": ErrorResponse,
        },
        409: {
            "description": "Entry already resolved",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def resolve_dlq_entry(
    dlq_service: DLQServiceDep,
    dlq_id: int = Path(..., description="DLQ entry ID to resolve", gt=0),
    request: ResolveDLQRequest | None = Body(None),
) -> DLQEntryResponse:
    """Mark a DLQ entry as resolved.

    Args:
        dlq_service: Injected DLQ service
        dlq_id: DLQ entry ID to resolve
        request: Optional resolution request with notes

    Returns:
        Updated DLQ entry response

    Raises:
        HTTPException 404: If entry not found
        HTTPException 409: If entry already resolved
        HTTPException 500: If resolution fails
    """
    return await resolve_dlq_entry_handler(dlq_id, dlq_service, request)


@router.get(
    "/stats",
    response_model=DLQStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get DLQ statistics",
    operation_id="getDLQStats",
    description="""
    Retrieve overall statistics about the Dead Letter Queue.

    Includes:
    - Total entries
    - Unresolved entries
    - Retry attempts and successes
    - Statistics by error category
    """,
    responses={
        200: {"description": "Statistics retrieved successfully"},
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def get_dlq_stats(
    dlq_service: DLQServiceDep,
) -> DLQStatsResponse:
    """Get DLQ statistics.

    Args:
        dlq_service: Injected DLQ service

    Returns:
        DLQ statistics response

    Raises:
        HTTPException 500: If stats retrieval fails
    """
    return await get_dlq_stats_handler(dlq_service)
