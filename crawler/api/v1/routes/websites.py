"""Website management routes for API v1."""

from fastapi import APIRouter, status

from crawler.api.schemas import ErrorResponse
from crawler.api.v1.dependencies import WebsiteServiceDep
from crawler.api.v1.handlers import create_website_handler
from crawler.api.v1.schemas import CreateWebsiteRequest, WebsiteResponse

router = APIRouter()


@router.post(
    "",
    response_model=WebsiteResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new website configuration",
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
