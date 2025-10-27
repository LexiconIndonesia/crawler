"""Website request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status

from crawler.api.v1.schemas import CreateWebsiteRequest, WebsiteResponse
from crawler.api.v1.services import WebsiteService
from crawler.api.validators import validate_and_calculate_next_run
from crawler.core.logging import get_logger

logger = get_logger(__name__)


async def create_website_handler(
    request: CreateWebsiteRequest,
    website_service: WebsiteService,
) -> WebsiteResponse:
    """Handle website creation with configuration and scheduling.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses.

    Args:
        request: Website creation request with configuration
        website_service: Injected website service

    Returns:
        Created website with scheduling information

    Raises:
        HTTPException: If validation fails or operation fails
    """
    logger.info("create_website_request", website_name=request.name, base_url=request.base_url)

    # Validate cron schedule
    is_valid, result = validate_and_calculate_next_run(request.schedule.cron)
    if not is_valid:
        logger.warning(
            "invalid_cron_expression",
            cron=request.schedule.cron,
            error=result,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression: {result}",
        )

    next_run_time = result if isinstance(result, datetime) else datetime.now(UTC)

    try:
        # Delegate to service layer (transaction managed by get_db dependency)
        return await website_service.create_website(request, next_run_time)

    except ValueError as e:
        # Business validation error (e.g., duplicate name)
        logger.warning("validation_error", error=str(e), website_name=request.name)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e

    except RuntimeError as e:
        # Service operation error
        logger.error("service_error", error=str(e), website_name=request.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        ) from e

    except Exception as e:
        # Unexpected error
        logger.error("unexpected_error", error=str(e), website_name=request.name)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}",
        ) from e
