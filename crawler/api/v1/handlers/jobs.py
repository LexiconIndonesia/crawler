"""Crawl job request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from fastapi import HTTPException, status

from crawler.api.generated import (
    CreateSeedJobInlineRequest,
    CreateSeedJobRequest,
    SeedJobResponse,
)
from crawler.api.v1.services import JobService
from crawler.core.logging import get_logger

logger = get_logger(__name__)


async def create_seed_job_handler(
    request: CreateSeedJobRequest,
    job_service: JobService,
) -> SeedJobResponse:
    """Handle seed job creation with HTTP error translation.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses.

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

    try:
        # Delegate to service layer (transaction managed by get_db dependency)
        return await job_service.create_seed_job(request)

    except ValueError as e:
        # Business validation error (e.g., website not found, inactive website)
        logger.warning("validation_error", error=str(e), **log_context)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    except RuntimeError as e:
        # Service operation error - log details but return generic message
        logger.error("service_error", error=str(e), exc_info=True, **log_context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the crawl job",
        ) from e

    except Exception as e:
        # Unexpected error - log with full stack trace but return generic message
        logger.error("unexpected_error", error=str(e), exc_info=True, **log_context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e


async def create_seed_job_inline_handler(
    request: CreateSeedJobInlineRequest,
    job_service: JobService,
) -> SeedJobResponse:
    """Handle seed job creation with inline configuration.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses.

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

    try:
        # Delegate to service layer (transaction managed by get_db dependency)
        return await job_service.create_seed_job_inline(request)

    except ValueError as e:
        # Business validation error (e.g., invalid configuration)
        logger.warning("validation_error", error=str(e), **log_context)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    except RuntimeError as e:
        # Service operation error - log details but return generic message
        logger.error("service_error", error=str(e), exc_info=True, **log_context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while creating the crawl job",
        ) from e

    except Exception as e:
        # Unexpected error - log with full stack trace but return generic message
        logger.error("unexpected_error", error=str(e), exc_info=True, **log_context)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred",
        ) from e
