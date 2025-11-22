"""Scheduled job management routes for API v1."""

from typing import Annotated

from fastapi import APIRouter, Path, Query, status

from crawler.api.generated import (
    ErrorResponse,
    ListScheduledJobsResponse,
    ScheduledJobResponse,
    UpdateScheduledJobRequest,
)
from crawler.api.v1.dependencies import ScheduledJobServiceDep
from crawler.api.v1.handlers import (
    delete_scheduled_job_handler,
    get_scheduled_job_handler,
    list_scheduled_jobs_handler,
    update_scheduled_job_handler,
)

router = APIRouter()


@router.get(
    "",
    response_model=ListScheduledJobsResponse,
    status_code=status.HTTP_200_OK,
    summary="List all scheduled jobs",
    operation_id="listScheduledJobs",
    description="""
    Retrieve a paginated list of scheduled jobs with optional filtering.

    This endpoint:
    1. Lists all scheduled jobs across websites or for a specific website
    2. Supports filtering by active status
    3. Returns pagination metadata (total, limit, offset)
    4. Includes website name for each job

    Filters:
    - `website_id`: Filter jobs for a specific website
    - `is_active`: Filter by active/inactive status
    """,
    responses={
        200: {"description": "Scheduled jobs retrieved successfully"},
        400: {
            "description": "Validation error",
            "model": ErrorResponse,
        },
        404: {
            "description": "Website not found (when filtering by website_id)",
            "model": ErrorResponse,
        },
    },
)
async def list_scheduled_jobs(
    service: ScheduledJobServiceDep,
    website_id: Annotated[
        str | None,
        Query(
            description="Filter by website ID",
            examples=["123e4567-e89b-12d3-a456-426614174000"],
        ),
    ] = None,
    is_active: Annotated[
        bool | None,
        Query(
            description="Filter by active status",
            examples=[True],
        ),
    ] = None,
    limit: Annotated[
        int,
        Query(
            ge=1,
            le=100,
            description="Maximum number of results to return",
            examples=[20],
        ),
    ] = 20,
    offset: Annotated[
        int,
        Query(
            ge=0,
            description="Number of results to skip for pagination",
            examples=[0],
        ),
    ] = 0,
) -> ListScheduledJobsResponse:
    """List all scheduled jobs with optional filtering.

    Args:
        service: Injected scheduled job service
        website_id: Optional website ID filter
        is_active: Optional active status filter
        limit: Maximum number of results
        offset: Number of results to skip

    Returns:
        Paginated list of scheduled jobs

    Raises:
        HTTPException: If validation fails or website not found
    """
    return await list_scheduled_jobs_handler(website_id, is_active, limit, offset, service)


@router.get(
    "/{id}",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Get scheduled job details",
    operation_id="getScheduledJob",
    description="""
    Retrieve detailed information about a specific scheduled job.

    This endpoint:
    1. Returns full job configuration including job_config JSONB
    2. Includes next run time and last run time
    3. Shows active status and timezone
    4. Provides website name and ID
    """,
    responses={
        200: {"description": "Scheduled job retrieved successfully"},
        404: {
            "description": "Scheduled job not found",
            "model": ErrorResponse,
        },
    },
)
async def get_scheduled_job(
    id: Annotated[
        str,
        Path(
            description="Scheduled job ID",
            examples=["123e4567-e89b-12d3-a456-426614174000"],
        ),
    ],
    service: ScheduledJobServiceDep,
) -> ScheduledJobResponse:
    """Get scheduled job details by ID.

    Args:
        id: Scheduled job ID
        service: Injected scheduled job service

    Returns:
        Scheduled job details

    Raises:
        HTTPException: If scheduled job not found
    """
    return await get_scheduled_job_handler(id, service)


@router.patch(
    "/{id}",
    response_model=ScheduledJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Update scheduled job",
    operation_id="updateScheduledJob",
    description="""
    Update scheduled job configuration.

    This endpoint:
    1. Validates cron expression if provided
    2. Automatically recalculates next_run_time when cron or timezone changes
    3. Allows pausing/resuming via is_active flag
    4. Supports updating job-specific configuration overrides

    All fields in the request are optional:
    - `cron_schedule`: Update the cron expression
    - `timezone`: Update the IANA timezone (e.g., "UTC", "America/New_York")
    - `is_active`: Pause (false) or resume (true) the schedule
    - `job_config`: Update job-specific configuration overrides
    """,
    responses={
        200: {"description": "Scheduled job updated successfully"},
        400: {
            "description": "Validation error or no changes detected",
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
                        "no_changes": {
                            "value": {
                                "detail": "No changes detected in the update request",
                                "error_code": "NO_CHANGES",
                            }
                        },
                    }
                }
            },
        },
        404: {
            "description": "Scheduled job not found",
            "model": ErrorResponse,
        },
    },
)
async def update_scheduled_job(
    id: Annotated[
        str,
        Path(
            description="Scheduled job ID",
            examples=["123e4567-e89b-12d3-a456-426614174000"],
        ),
    ],
    request: UpdateScheduledJobRequest,
    service: ScheduledJobServiceDep,
) -> ScheduledJobResponse:
    """Update scheduled job configuration.

    Args:
        id: Scheduled job ID
        request: Update request with optional fields
        service: Injected scheduled job service

    Returns:
        Updated scheduled job details

    Raises:
        HTTPException: If validation fails or scheduled job not found
    """
    return await update_scheduled_job_handler(id, request, service)


@router.delete(
    "/{id}",
    status_code=status.HTTP_200_OK,
    summary="Delete scheduled job",
    operation_id="deleteScheduledJob",
    description="""
    Delete a scheduled job.

    This endpoint:
    1. Permanently removes the scheduled job
    2. Does NOT delete the website configuration
    3. Returns confirmation with job and website IDs

    Note: Deleting a scheduled job stops future automatic crawls but
    does not affect the website configuration. Manual crawls via
    trigger endpoint will still work.
    """,
    responses={
        200: {
            "description": "Scheduled job deleted successfully",
            "content": {
                "application/json": {
                    "example": {
                        "message": (
                            "Scheduled job '123e4567-e89b-12d3-a456-426614174000' "
                            "deleted successfully"
                        ),
                        "id": "123e4567-e89b-12d3-a456-426614174000",
                        "website_id": "987fcdeb-51a2-43f1-b456-426614174999",
                    }
                }
            },
        },
        404: {
            "description": "Scheduled job not found",
            "model": ErrorResponse,
        },
    },
)
async def delete_scheduled_job(
    id: Annotated[
        str,
        Path(
            description="Scheduled job ID",
            examples=["123e4567-e89b-12d3-a456-426614174000"],
        ),
    ],
    service: ScheduledJobServiceDep,
) -> dict:
    """Delete scheduled job.

    Args:
        id: Scheduled job ID
        service: Injected scheduled job service

    Returns:
        Deletion confirmation message

    Raises:
        HTTPException: If scheduled job not found
    """
    return await delete_scheduled_job_handler(id, service)
