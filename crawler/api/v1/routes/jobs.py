"""Crawl job management routes for API v1."""

from fastapi import APIRouter, status

from crawler.api.generated import CreateSeedJobRequest, SeedJobResponse
from crawler.api.schemas import ErrorResponse
from crawler.api.v1.dependencies import JobServiceDep
from crawler.api.v1.handlers import create_seed_job_handler

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
