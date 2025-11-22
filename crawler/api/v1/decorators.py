"""API handler decorators for common patterns.

This module provides reusable decorators for API handlers to reduce code duplication
and ensure consistent error handling across endpoints.
"""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import ParamSpec, TypeVar

from fastapi import HTTPException, status

from crawler.core.logging import get_logger

logger = get_logger(__name__)

P = ParamSpec("P")
R = TypeVar("R")


def handle_service_errors(
    operation: str = "operation",
) -> Callable[[Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]]:
    """Decorator to centralize service-layer error handling in API handlers.

    This decorator handles common exception patterns from service layer operations
    and translates them to appropriate HTTP exceptions with consistent logging.

    Exception handling:
    - ValueError: Business validation errors → 400 Bad Request with error message
    - RuntimeError: Service operation errors → 500 with generic message
    - Exception: Unexpected errors → 500 with generic message

    Args:
        operation: Description of the operation for error messages (e.g., "creating the crawl job")

    Returns:
        Decorator function

    Example:
        @handle_service_errors(operation="creating the crawl job")
        async def create_seed_job_handler(
            request: CreateSeedJobRequest,
            job_service: JobService,
        ) -> SeedJobResponse:
            log_context = {"website_id": str(request.website_id)}
            logger.info("create_seed_job_request", **log_context)
            return await job_service.create_seed_job(request)
    """

    def decorator(func: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                return await func(*args, **kwargs)

            except ValueError as e:
                # Check if this is a "not found" error (should be 404, not 400)
                error_msg = str(e).lower()
                is_not_found = "not found" in error_msg and (
                    "job with id" in error_msg
                    or "job id" in error_msg
                    or "entry with id" in error_msg
                    or "dlq entry" in error_msg
                    or "website with id" in error_msg
                    or "scheduled job with id" in error_msg
                )

                if is_not_found:
                    # Resource not found - return 404
                    logger.warning(
                        "resource_not_found",
                        error=str(e),
                        handler=func.__name__,
                    )
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=str(e),
                    ) from e

                # Business validation error (e.g., invalid configuration, inactive website)
                logger.warning(
                    "validation_error",
                    error=str(e),
                    handler=func.__name__,
                )
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                ) from e

            except RuntimeError as e:
                # Service operation error - log details but return generic message
                logger.error(
                    "service_error",
                    error=str(e),
                    handler=func.__name__,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"An error occurred while {operation}",
                ) from e

            except HTTPException:
                # Re-raise HTTPExceptions as-is (already handled)
                raise

            except Exception as e:
                # Unexpected error - log with full stack trace but return generic message
                logger.error(
                    "unexpected_error",
                    error=str(e),
                    handler=func.__name__,
                    exc_info=True,
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="An unexpected error occurred",
                ) from e

        return wrapper

    return decorator
