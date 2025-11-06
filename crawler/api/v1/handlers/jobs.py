"""Crawl job request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from crawler.api.generated import (
    CancelJobRequest,
    CancelJobResponse,
    CreateSeedJobInlineRequest,
    CreateSeedJobRequest,
    SeedJobResponse,
)
from crawler.api.v1.decorators import handle_service_errors
from crawler.api.v1.services import JobService
from crawler.core.logging import get_logger

logger = get_logger(__name__)


@handle_service_errors(operation="creating the crawl job")
async def create_seed_job_handler(
    request: CreateSeedJobRequest,
    job_service: JobService,
) -> SeedJobResponse:
    """Handle seed job creation with HTTP error translation.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses via the decorator.

    Args:
        request: Seed job creation request
        job_service: Injected job service

    Returns:
        Created seed job with ID and status

    Raises:
        HTTPException: If validation fails or operation fails
    """
    log_context = {
        "website_id": str(request.website_id),
        "seed_url": str(request.seed_url),
        "priority": request.priority,
    }
    logger.info("create_seed_job_request", **log_context)

    # Delegate to service layer (error handling done by decorator)
    return await job_service.create_seed_job(request)


@handle_service_errors(operation="creating the crawl job")
async def create_seed_job_inline_handler(
    request: CreateSeedJobInlineRequest,
    job_service: JobService,
) -> SeedJobResponse:
    """Handle seed job creation with inline configuration.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses via the decorator.

    Args:
        request: Seed job creation request with inline configuration
        job_service: Injected job service

    Returns:
        Created seed job with ID and status

    Raises:
        HTTPException: If validation fails or operation fails
    """
    log_context = {
        "seed_url": str(request.seed_url),
        "priority": request.priority,
        "num_steps": len(request.steps),
    }
    logger.info("create_seed_job_inline_request", **log_context)

    # Delegate to service layer (error handling done by decorator)
    return await job_service.create_seed_job_inline(request)


@handle_service_errors(operation="cancelling the job")
async def cancel_job_handler(
    job_id: str,
    request: CancelJobRequest,
    job_service: JobService,
) -> CancelJobResponse:
    """Handle job cancellation with HTTP error translation.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses via the decorator.

    Args:
        job_id: Job ID to cancel
        request: Cancellation request with optional reason
        job_service: Injected job service

    Returns:
        Cancellation response with updated job status

    Raises:
        HTTPException: If job not found or cannot be cancelled
    """
    log_context = {
        "job_id": job_id,
        "reason": request.reason,
    }
    logger.info("cancel_job_request", **log_context)

    # Delegate to service layer (error handling done by decorator)
    return await job_service.cancel_job(job_id, request)
