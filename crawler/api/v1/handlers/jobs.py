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
    WSTokenResponse,
)
from crawler.api.v1.decorators import handle_service_errors
from crawler.api.v1.services import JobService
from crawler.core.logging import get_logger
from crawler.db.repositories import CrawlJobRepository
from crawler.services.redis_cache import WebSocketTokenService

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


@handle_service_errors(operation="generating WebSocket token")
async def generate_ws_token_handler(
    job_id: str,
    crawl_job_repo: CrawlJobRepository,
    ws_token_service: WebSocketTokenService,
) -> WSTokenResponse:
    """Handle WebSocket token generation with HTTP error translation.

    This handler validates the job exists, generates a token, and returns it.

    Args:
        job_id: Job ID to generate token for
        crawl_job_repo: Injected crawl job repository
        ws_token_service: Injected WebSocket token service

    Returns:
        Token response with token and expiry

    Raises:
        HTTPException: If job not found or token generation fails
    """
    logger.info("ws_token_request", job_id=job_id)

    # Guard: check if job exists
    job = await crawl_job_repo.get_by_id(job_id)
    if not job:
        raise ValueError(f"Job with ID '{job_id}' not found")

    # Generate token
    token = await ws_token_service.create_token(job_id)

    logger.info("ws_token_generated", job_id=job_id)

    return WSTokenResponse(
        token=token,
        expires_in=600,  # 10 minutes
        job_id=job.id,  # Use UUID from job object for type safety
    )
