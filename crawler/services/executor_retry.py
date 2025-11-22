"""Retry logic for executor requests.

This module provides request-level retry logic with exponential backoff for
HTTP/API/Browser executors. It uses GlobalConfig.retry settings to determine
retry behavior.
"""

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any, TypeVar

from crawler.core.logging import get_logger
from crawler.services.retry_policy import (
    BackoffStrategyEnum,
    ErrorCategoryEnum,
    calculate_backoff,
    classify_exception,
    classify_http_status,
)

logger = get_logger(__name__)

T = TypeVar("T")


async def execute_with_retry(
    func: Callable[[], Awaitable[T]],
    retry_config: dict[str, Any] | None,
    operation_name: str,
    url: str,
) -> T:
    """Execute a function with retry logic based on GlobalConfig.retry.

    Args:
        func: Async function to execute (should return ExecutionResult)
        retry_config: GlobalConfig.retry dict or None
        operation_name: Name of operation for logging (e.g., "http_request", "browser_navigate")
        url: Target URL for logging

    Returns:
        Result from func() after successful execution

    Raises:
        Exception: If all retry attempts fail, raises the last exception

    Example:
        >>> retry_config = {"max_attempts": 3, "backoff_strategy": "exponential", ...}
        >>> result = await execute_with_retry(
        ...     lambda: executor.execute(url, config, selectors),
        ...     retry_config,
        ...     "http_request",
        ...     url
        ... )
    """
    # Guard: no retry config - execute once
    if not retry_config or not isinstance(retry_config, dict):
        return await func()

    # Extract retry configuration
    max_attempts = retry_config.get("max_attempts", 1)
    initial_delay = retry_config.get("initial_delay_seconds", 1)
    max_delay = retry_config.get("max_delay_seconds", 60)
    backoff_strategy_str = retry_config.get("backoff_strategy", "exponential")
    backoff_multiplier = retry_config.get("backoff_multiplier", 2.0)

    # Convert backoff_strategy to enum
    try:
        if isinstance(backoff_strategy_str, BackoffStrategyEnum):
            backoff_strategy = backoff_strategy_str
        else:
            backoff_strategy = BackoffStrategyEnum(backoff_strategy_str)
    except ValueError:
        logger.warning(
            "invalid_backoff_strategy",
            strategy=backoff_strategy_str,
            using_default="exponential",
        )
        backoff_strategy = BackoffStrategyEnum.EXPONENTIAL

    # Guard: max_attempts = 1 means no retries
    if max_attempts <= 1:
        return await func()

    # Attempt execution with retries
    last_exception: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(
                "executor_attempt",
                operation=operation_name,
                url=url,
                attempt=attempt,
                max_attempts=max_attempts,
            )

            result = await func()

            # Check if result indicates retriable failure
            # ExecutionResult has an 'error' field - if present, it's a failure
            if hasattr(result, "error") and result.error:
                # Classify error to determine if retryable
                error_category = _classify_result_error(result)
                is_retryable = _is_retryable_error(error_category)

                if not is_retryable:
                    # Permanent error - don't retry
                    logger.info(
                        "executor_permanent_error_no_retry",
                        operation=operation_name,
                        url=url,
                        error_category=error_category.value,
                        error=result.error,
                    )
                    return result

                # Retryable error - log and retry if attempts remain
                if attempt < max_attempts:
                    delay = calculate_backoff(
                        strategy=backoff_strategy,
                        attempt=attempt,
                        initial_delay=initial_delay,
                        max_delay=max_delay,
                        multiplier=backoff_multiplier,
                        apply_jitter=True,
                    )

                    logger.warning(
                        "executor_retryable_error_will_retry",
                        operation=operation_name,
                        url=url,
                        attempt=attempt,
                        max_attempts=max_attempts,
                        error_category=error_category.value,
                        error=result.error,
                        delay_seconds=delay,
                    )

                    await asyncio.sleep(delay)
                    continue  # Retry
                else:
                    # Last attempt failed
                    logger.error(
                        "executor_all_retries_exhausted",
                        operation=operation_name,
                        url=url,
                        attempts=max_attempts,
                        error_category=error_category.value,
                        error=result.error,
                    )
                    return result

            # Success - return result
            if attempt > 1:
                logger.info(
                    "executor_retry_succeeded",
                    operation=operation_name,
                    url=url,
                    attempt=attempt,
                )
            return result

        except Exception as e:
            last_exception = e

            # Classify exception to determine if retryable
            error_category = classify_exception(e, log_decision=False)
            is_retryable = _is_retryable_error(error_category)

            if not is_retryable:
                # Permanent exception - don't retry
                logger.error(
                    "executor_permanent_exception_no_retry",
                    operation=operation_name,
                    url=url,
                    error_category=error_category.value,
                    exception=type(e).__name__,
                    error=str(e),
                )
                raise

            # Retryable exception - retry if attempts remain
            if attempt < max_attempts:
                delay = calculate_backoff(
                    strategy=backoff_strategy,
                    attempt=attempt,
                    initial_delay=initial_delay,
                    max_delay=max_delay,
                    multiplier=backoff_multiplier,
                    apply_jitter=True,
                )

                logger.warning(
                    "executor_retryable_exception_will_retry",
                    operation=operation_name,
                    url=url,
                    attempt=attempt,
                    max_attempts=max_attempts,
                    error_category=error_category.value,
                    exception=type(e).__name__,
                    error=str(e),
                    delay_seconds=delay,
                )

                await asyncio.sleep(delay)
                # Continue to next attempt
            else:
                # Last attempt - raise exception
                logger.error(
                    "executor_all_retries_exhausted_exception",
                    operation=operation_name,
                    url=url,
                    attempts=max_attempts,
                    error_category=error_category.value,
                    exception=type(e).__name__,
                    error=str(e),
                )
                raise

    # Should never reach here, but if we do, raise the last exception
    if last_exception:
        raise last_exception

    # This should be unreachable
    raise RuntimeError("Unexpected code path in execute_with_retry")


def _classify_result_error(result: Any) -> ErrorCategoryEnum:
    """Classify error from ExecutionResult.

    Args:
        result: ExecutionResult with error field

    Returns:
        ErrorCategoryEnum for the error
    """
    # Check if result has status_code (HTTP/API errors)
    if hasattr(result, "status_code") and result.status_code:
        return classify_http_status(result.status_code, log_decision=False)

    # Check if result has metadata with error_type (from executor)
    if hasattr(result, "metadata") and result.metadata:
        error_type = result.metadata.get("error_type")
        if error_type == "retryable":
            return ErrorCategoryEnum.NETWORK
        elif error_type == "permanent":
            return ErrorCategoryEnum.CLIENT_ERROR

    # Default to unknown (will be treated as non-retryable)
    return ErrorCategoryEnum.UNKNOWN


def _is_retryable_error(error_category: ErrorCategoryEnum) -> bool:
    """Determine if error category is retryable.

    Args:
        error_category: Error category from classification

    Returns:
        True if retryable, False otherwise
    """
    retryable_categories = {
        ErrorCategoryEnum.NETWORK,
        ErrorCategoryEnum.TIMEOUT,
        ErrorCategoryEnum.SERVER_ERROR,
        ErrorCategoryEnum.RATE_LIMIT,
        ErrorCategoryEnum.BROWSER_CRASH,
        ErrorCategoryEnum.RESOURCE_UNAVAILABLE,
    }

    return error_category in retryable_categories
