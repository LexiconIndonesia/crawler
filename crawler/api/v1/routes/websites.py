"""Website management routes for API v1."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from crawler.api.generated import (
    CreateWebsiteRequest,
    ErrorResponse,
    ListWebsitesResponse,
    UpdateWebsiteRequest,
    UpdateWebsiteResponse,
    WebsiteResponse,
    WebsiteWithStatsResponse,
)
from crawler.api.v1.dependencies import WebsiteServiceDep
from crawler.api.v1.handlers import (
    create_website_handler,
    delete_website_handler,
    get_website_by_id_handler,
    list_websites_handler,
    update_website_handler,
)

router = APIRouter()


@router.post(
    "",
    response_model=WebsiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new website configuration",
    operation_id="createWebsite",
    description="""
    Create a new website with crawl configuration and schedule.

    This endpoint:
    1. Validates the website configuration including selectors and steps
    2. Validates the cron schedule expression
    3. Stores the configuration in PostgreSQL
    4. Creates a scheduled job if schedule is enabled
    5. Returns the created website with ID and next run time

    The configuration includes:
    - Steps for crawling/scraping (API, Browser, or HTTP methods)
    - Selectors for data extraction
    - Schedule configuration with cron expression
    - Global settings (rate limits, timeouts, retries)
    - Variables for dynamic value substitution
    """,
    responses={
        201: {"description": "Website created successfully"},
        400: {
            "description": "Validation error",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_cron": {
                            "value": {
                                "detail": "Invalid cron expression: expected 5 fields, got 3",
                                "error_code": "INVALID_CRON_EXPRESSION",
                            }
                        },
                        "duplicate_name": {
                            "value": {
                                "detail": "Website with name 'Example Site' already exists",
                                "error_code": "DUPLICATE_WEBSITE_NAME",
                            }
                        },
                    }
                }
            },
        },
        422: {"description": "Validation error (invalid request body)"},
    },
)
async def create_website(
    request: CreateWebsiteRequest,
    website_service: WebsiteServiceDep,
) -> WebsiteResponse:
    """Create a new website configuration with recurring crawl schedule.

    Args:
        request: Website creation request with configuration
        website_service: Injected website service

    Returns:
        Created website with scheduling information

    Raises:
        HTTPException: If validation fails or website name already exists
    """
    return await create_website_handler(request, website_service)


@router.get(
    "",
    response_model=ListWebsitesResponse,
    status_code=status.HTTP_200_OK,
    summary="List all website configurations",
    operation_id="listWebsites",
    description="""
    Retrieve a paginated list of website configurations with optional filtering.

    This endpoint:
    1. Retrieves websites with pagination support
    2. Optionally filters by status (active, inactive)
    3. Returns basic website information
    4. Includes total count for pagination

    Filtering:
    - status: Filter by website status (active/inactive)

    Pagination:
    - limit: Number of results per page (default: 20, max: 100)
    - offset: Number of results to skip
    """,
)
async def list_websites(
    website_service: WebsiteServiceDep,
    status: Annotated[
        str | None,
        Query(description="Filter by website status", examples=["active"]),
    ] = None,
    limit: Annotated[
        int, Query(ge=1, le=100, description="Number of websites to return (max 100)")
    ] = 20,
    offset: Annotated[
        int, Query(ge=0, description="Number of websites to skip for pagination")
    ] = 0,
) -> ListWebsitesResponse:
    """List all websites with pagination and filtering.

    Args:
        website_service: Injected website service
        status: Optional status filter ('active' or 'inactive')
        limit: Maximum number of results (default: 20, max: 100)
        offset: Number of results to skip (default: 0)

    Returns:
        Paginated list of websites with total count

    Raises:
        HTTPException: If invalid parameters or operation fails
    """
    return await list_websites_handler(status, limit, offset, website_service)


@router.get(
    "/{id}",
    response_model=WebsiteWithStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get website configuration by ID",
    operation_id="getWebsiteById",
    description="""
    Retrieve a single website configuration by ID with statistics.

    This endpoint:
    1. Retrieves website configuration and metadata
    2. Calculates statistics from crawl history:
       - Total crawl jobs executed
       - Success rate (completed jobs / total jobs)
       - Total pages crawled across all jobs
       - Last successful crawl timestamp
       - Next scheduled run time

    Statistics are calculated from the database and reflect historical data.
    """,
    responses={
        200: {"description": "Website retrieved successfully"},
        404: {
            "description": "Website not found",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "Website with ID '550e8400-e29b-41d4-a716-446655440000' not found"
                        ),
                        "error_code": "WEBSITE_NOT_FOUND",
                    }
                }
            },
        },
        422: {"description": "Validation error (invalid UUID format)"},
    },
)
async def get_website_by_id(
    id: Annotated[
        str, Path(description="Website ID", examples=["550e8400-e29b-41d4-a716-446655440000"])
    ],
    website_service: WebsiteServiceDep,
) -> WebsiteWithStatsResponse:
    """Get a single website configuration by ID with statistics.

    Args:
        id: Website ID (UUID format)
        website_service: Injected website service

    Returns:
        Website configuration with statistics

    Raises:
        HTTPException: If website not found or operation fails
    """
    return await get_website_by_id_handler(id, website_service)


@router.put(
    "/{id}",
    response_model=UpdateWebsiteResponse,
    status_code=status.HTTP_200_OK,
    summary="Update website configuration",
    operation_id="updateWebsite",
    description="""
    Update an existing website configuration with versioning and optional re-crawl.

    This endpoint:
    1. Validates the updated configuration
    2. Saves the current configuration as a new version in history
    3. Updates the website with new configuration
    4. Updates scheduled jobs if schedule changed
    5. Optionally triggers an immediate re-crawl
    6. Returns the updated website with version info

    Configuration versioning:
    - Every update creates a new version in the history table
    - Each version tracks the old configuration, who changed it, and why
    - You can rollback to previous versions using the version history

    Re-crawl behavior:
    - Set `trigger_recrawl: true` to create a one-time crawl job
    - The job uses the new configuration immediately
    - Useful for testing configuration changes
    """,
    responses={
        200: {"description": "Website updated successfully"},
        400: {
            "description": "Validation error or no changes detected",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "no_changes": {
                            "value": {
                                "detail": "No changes detected in the update request",
                                "error_code": "NO_CHANGES_DETECTED",
                            }
                        },
                        "invalid_cron": {
                            "value": {
                                "detail": "Invalid cron expression: expected 5 fields, got 3",
                                "error_code": "INVALID_CRON_EXPRESSION",
                            }
                        },
                        "duplicate_name": {
                            "value": {
                                "detail": "Website with name 'Example Site' already exists",
                                "error_code": "DUPLICATE_WEBSITE_NAME",
                            }
                        },
                    }
                }
            },
        },
        404: {
            "description": "Website not found",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": (
                            "Website with ID '550e8400-e29b-41d4-a716-446655440000' not found"
                        ),
                        "error_code": "WEBSITE_NOT_FOUND",
                    }
                }
            },
        },
        422: {"description": "Validation error"},
    },
)
async def update_website(
    id: Annotated[str, Path(description="Website ID")],
    request: UpdateWebsiteRequest,
    website_service: WebsiteServiceDep,
) -> UpdateWebsiteResponse:
    """Update a website configuration with versioning.

    Args:
        id: Website ID (UUID format)
        request: Update request with new configuration
        website_service: Injected website service

    Returns:
        Updated website configuration with version info

    Raises:
        HTTPException: If website not found or validation fails
    """
    return await update_website_handler(id, request, website_service)


@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Delete website (soft delete)",
    operation_id="deleteWebsite",
    description="""
    Soft delete a website and cancel all running jobs.

    This endpoint:
    1. Validates the website exists and is not already deleted
    2. Cancels all active (pending/running) jobs for this website
    3. Archives the current configuration for audit purposes
    4. Soft deletes the website (sets deleted_at timestamp)
    5. Sets status to 'inactive'
    6. Returns deletion summary with cancelled jobs

    Soft delete behavior:
    - Website is not permanently removed from the database
    - Sets `deleted_at` timestamp to current time
    - Sets status to 'inactive'
    - Configuration is preserved in history table
    - Can be restored by clearing deleted_at (not yet implemented)

    Job cancellation:
    - All pending and running jobs are automatically cancelled
    - Jobs are marked with cancellation reason
    - Returns list of cancelled job IDs

    Future feature (delete_data parameter):
    - Option to delete all crawled pages and data (not yet implemented)
    - When true, removes all crawled_page entries
    - When false (default), preserves crawled data for audit
    """,
    responses={
        200: {
            "description": "Website deleted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "550e8400-e29b-41d4-a716-446655440000",
                        "name": "Example Website",
                        "deleted_at": "2025-11-09T12:00:00Z",
                        "cancelled_jobs": 2,
                        "cancelled_job_ids": [
                            "660e8400-e29b-41d4-a716-446655440000",
                            "770e8400-e29b-41d4-a716-446655440000",
                        ],
                        "config_archived_version": 5,
                        "message": "Website 'Example Website' deleted successfully",
                    }
                }
            },
        },
        400: {
            "description": "Website not found or already deleted",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "not_found": {
                            "value": {
                                "detail": (
                                    "Website with ID '550e8400-e29b-41d4-a716-446655440000' "
                                    "not found"
                                ),
                                "error_code": "WEBSITE_NOT_FOUND",
                            }
                        },
                        "already_deleted": {
                            "value": {
                                "detail": (
                                    "Website with ID '550e8400-e29b-41d4-a716-446655440000' "
                                    "is already deleted"
                                ),
                                "error_code": "WEBSITE_ALREADY_DELETED",
                            }
                        },
                    }
                }
            },
        },
        422: {"description": "Validation error"},
    },
)
async def delete_website(
    id: Annotated[str, Path(description="Website ID")],
    website_service: WebsiteServiceDep,
    delete_data: Annotated[
        bool,
        Query(
            description=("Delete all crawled data (not yet implemented, reserved for future use)")
        ),
    ] = False,
) -> dict:
    """Delete a website with soft delete.

    Args:
        id: Website ID (UUID format)
        website_service: Injected website service
        delete_data: Whether to delete all crawled data (not yet implemented)

    Returns:
        Deletion summary including cancelled jobs and archived config version

    Raises:
        HTTPException: If website not found or already deleted
    """
    return await delete_website_handler(id, delete_data, website_service)
