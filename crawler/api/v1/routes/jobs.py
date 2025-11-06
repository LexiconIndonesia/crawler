"""Crawl job management routes for API v1."""

from fastapi import APIRouter, status

from crawler.api.generated import (
    CancelJobRequest,
    CancelJobResponse,
    CreateSeedJobInlineRequest,
    CreateSeedJobRequest,
    ErrorResponse,
    SeedJobResponse,
)
from crawler.api.v1.dependencies import JobServiceDep
from crawler.api.v1.handlers import (
    cancel_job_handler,
    create_seed_job_handler,
    create_seed_job_inline_handler,
)

router = APIRouter()


@router.post(
    "/seed",
    response_model=SeedJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a seed URL for crawling using an existing website template",
    operation_id="createSeedJob",
    description="""
    Create a one-time crawl job using an existing website template configuration.

    This endpoint:
    1. Validates the seed URL and website_id
    2. Loads the website configuration from database
    3. Optionally accepts variable substitutions
    4. Creates a crawl job with pending status
    5. Returns job ID and status for tracking

    The job will use the website template's configuration including:
    - Crawl/scrape steps
    - Selectors for data extraction
    - Global settings (rate limits, timeouts, retries)
    - Browser configuration if needed

    Variables provided in the request will override template variables.
    """,
    responses={
        201: {"description": "Crawl job created successfully"},
        400: {
            "description": "Validation error",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "website_not_found": {
                            "value": {
                                "detail": (
                                    "Website with ID '550e8400-e29b-41d4-a716-446655440000' not "
                                    "found"
                                ),
                                "error_code": "WEBSITE_NOT_FOUND",
                            }
                        },
                        "invalid_url": {
                            "value": {
                                "detail": "seed_url must be a valid URL starting with http:// or "
                                "https://",
                                "error_code": "INVALID_URL",
                                "field": "seed_url",
                            }
                        },
                        "inactive_website": {
                            "value": {
                                "detail": "Website 'Example Site' is inactive and cannot be used",
                                "error_code": "WEBSITE_INACTIVE",
                            }
                        },
                    }
                }
            },
        },
        422: {"description": "Validation error (invalid request body)"},
    },
)
async def create_seed_job(
    request: CreateSeedJobRequest,
    job_service: JobServiceDep,
) -> SeedJobResponse:
    """Create a new crawl job using a website template.

    Args:
        request: Seed job creation request with website_id and seed_url
        job_service: Injected job service

    Returns:
        Created crawl job with ID and status

    Raises:
        HTTPException: If validation fails or website not found
    """
    return await create_seed_job_handler(request, job_service)


@router.post(
    "/seed-inline",
    response_model=SeedJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a seed URL for crawling with inline configuration",
    operation_id="createSeedJobInline",
    description="""
    Create a one-time crawl job with full inline configuration (Mode B - no template).

    This endpoint:
    1. Validates the seed URL and inline configuration
    2. Validates crawl steps and selectors
    3. Creates a crawl job with embedded configuration
    4. Returns job ID and status for tracking

    Unlike the template-based endpoint, this allows ad-hoc crawls without
    creating a website configuration first. The configuration is provided
    inline and stored with the job.

    Use cases:
    - One-off data collection tasks
    - Testing crawl configurations before creating a template
    - Dynamic crawling with programmatically generated configs
    - External integrations that generate configurations on-the-fly
    """,
    responses={
        201: {"description": "Crawl job created successfully"},
        400: {
            "description": "Validation error",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "invalid_url": {
                            "value": {
                                "detail": "seed_url must be a valid URL starting with http:// or "
                                "https://",
                                "error_code": "INVALID_URL",
                                "field": "seed_url",
                            }
                        },
                        "invalid_config": {
                            "value": {
                                "detail": "Invalid step configuration: missing required field "
                                "'method'",
                                "error_code": "INVALID_CONFIGURATION",
                                "field": "steps",
                            }
                        },
                        "empty_steps": {
                            "value": {
                                "detail": "At least one crawl step is required",
                                "error_code": "VALIDATION_ERROR",
                                "field": "steps",
                            }
                        },
                    }
                }
            },
        },
        422: {"description": "Validation error (invalid request body)"},
    },
)
async def create_seed_job_inline(
    request: CreateSeedJobInlineRequest,
    job_service: JobServiceDep,
) -> SeedJobResponse:
    """Create a new crawl job with inline configuration.

    Args:
        request: Seed job creation request with inline configuration
        job_service: Injected job service

    Returns:
        Created crawl job with ID and status

    Raises:
        HTTPException: If validation fails or configuration is invalid
    """
    return await create_seed_job_inline_handler(request, job_service)


@router.post(
    "/{job_id}/cancel",
    response_model=CancelJobResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel a crawl job",
    operation_id="cancelJob",
    description="""
    Cancel a running or pending crawl job.

    This endpoint validates that the job exists and is not already completed or cancelled,
    then updates the job status to "cancelled" and sets a Redis cancellation flag for
    workers to detect.

    Jobs in "completed" or "failed" status cannot be cancelled.
    """,
    responses={
        200: {"description": "Job cancellation initiated successfully"},
        400: {
            "description": "Job cannot be cancelled",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "already_completed": {
                            "value": {
                                "detail": "Job is already completed and cannot be cancelled",
                                "error_code": "INVALID_JOB_STATUS",
                            }
                        },
                        "already_cancelled": {
                            "value": {
                                "detail": "Job is already cancelled",
                                "error_code": "ALREADY_CANCELLED",
                            }
                        },
                    }
                }
            },
        },
        404: {
            "description": "Job not found",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "examples": {
                        "not_found": {
                            "value": {
                                "detail": "Job with ID '770e8400-e29b-41d4-a716-446655440000' not "
                                "found",
                                "error_code": "JOB_NOT_FOUND",
                            }
                        }
                    }
                }
            },
        },
        422: {"description": "Validation error (invalid request body)"},
    },
)
async def cancel_job(
    job_id: str,
    request: CancelJobRequest,
    job_service: JobServiceDep,
) -> CancelJobResponse:
    """Cancel a crawl job.

    Args:
        job_id: Job ID to cancel
        request: Cancellation request with optional reason
        job_service: Injected job service

    Returns:
        Cancellation response with updated job status

    Raises:
        HTTPException: If job not found or cannot be cancelled
    """
    return await cancel_job_handler(job_id, request, job_service)
