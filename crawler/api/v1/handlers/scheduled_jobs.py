"""Scheduled job request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from crawler.api.generated import (
    ListScheduledJobsResponse,
    ScheduledJobResponse,
    UpdateScheduledJobRequest,
)
from crawler.api.v1.decorators import handle_service_errors
from crawler.api.v1.services import ScheduledJobService
from crawler.core.logging import get_logger

logger = get_logger(__name__)


@handle_service_errors(operation="listing scheduled jobs")
async def list_scheduled_jobs_handler(
    website_id: str | None,
    is_active: bool | None,
    limit: int,
    offset: int,
    service: ScheduledJobService,
) -> ListScheduledJobsResponse:
    """Handle list scheduled jobs request.

    This handler delegates to the service layer which handles:
    - Website validation (if filter provided)
    - Job listing with filters
    - Pagination

    Args:
        website_id: Optional website ID filter
        is_active: Optional active status filter
        limit: Maximum number of results
        offset: Number of results to skip
        service: Injected scheduled job service

    Returns:
        Paginated list of scheduled jobs

    Raises:
        HTTPException: If validation fails or operation fails
            - 400: Invalid website_id
            - 404: Website not found (if filter provided)
            - 500: Service operation failure
    """
    logger.info(
        "list_scheduled_jobs_request",
        website_id=website_id,
        is_active=is_active,
        limit=limit,
        offset=offset,
    )

    # Delegate to service layer (error handling done by decorator)
    return await service.list_scheduled_jobs(website_id, is_active, limit, offset)


@handle_service_errors(operation="fetching scheduled job")
async def get_scheduled_job_handler(
    job_id: str, service: ScheduledJobService
) -> ScheduledJobResponse:
    """Handle get scheduled job request.

    This handler delegates to the service layer which handles:
    - Job lookup
    - Website name retrieval

    Args:
        job_id: Scheduled job ID
        service: Injected scheduled job service

    Returns:
        Scheduled job details with full job_config

    Raises:
        HTTPException: If validation fails or operation fails
            - 404: Scheduled job not found
            - 500: Service operation failure
    """
    logger.info("get_scheduled_job_request", job_id=job_id)

    # Delegate to service layer (error handling done by decorator)
    return await service.get_scheduled_job(job_id)


@handle_service_errors(operation="updating scheduled job")
async def update_scheduled_job_handler(
    job_id: str, request: UpdateScheduledJobRequest, service: ScheduledJobService
) -> ScheduledJobResponse:
    """Handle update scheduled job request.

    This handler delegates to the service layer which handles:
    - Job lookup
    - Cron expression validation
    - Next run time calculation
    - Job update with new configuration

    Args:
        job_id: Scheduled job ID
        request: Update request with optional fields
        service: Injected scheduled job service

    Returns:
        Updated scheduled job details

    Raises:
        HTTPException: If validation fails or operation fails
            - 400: Invalid cron expression or no changes detected
            - 404: Scheduled job not found
            - 500: Service operation failure
    """
    logger.info("update_scheduled_job_request", job_id=job_id)

    # Delegate to service layer (error handling done by decorator)
    return await service.update_scheduled_job(job_id, request)


@handle_service_errors(operation="deleting scheduled job")
async def delete_scheduled_job_handler(job_id: str, service: ScheduledJobService) -> dict:
    """Handle delete scheduled job request.

    This handler delegates to the service layer which handles:
    - Job lookup
    - Job deletion

    Args:
        job_id: Scheduled job ID
        service: Injected scheduled job service

    Returns:
        Deletion confirmation message

    Raises:
        HTTPException: If validation fails or operation fails
            - 404: Scheduled job not found
            - 500: Service operation failure
    """
    logger.info("delete_scheduled_job_request", job_id=job_id)

    # Delegate to service layer (error handling done by decorator)
    return await service.delete_scheduled_job(job_id)
