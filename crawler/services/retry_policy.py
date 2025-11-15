"""Retry policy service with error classification and backoff calculation.

This module provides:
1. Error classification (HTTP status codes, exceptions → ErrorCategory)
2. Backoff delay calculation (exponential, linear, fixed) with jitter
3. Retry-After header parsing for server-specified delays
4. Retry policy lookup and management
"""

from __future__ import annotations

import random
import traceback
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

from crawler.core.logging import get_logger
from crawler.db.generated.models import BackoffStrategyEnum, ErrorCategoryEnum

if TYPE_CHECKING:
    from crawler.db.repositories.retry_policy import RetryPolicyRepository

logger = get_logger(__name__)


# ============================================================================
# Error Classification
# ============================================================================


def classify_http_status(status_code: int) -> ErrorCategoryEnum:
    """Classify HTTP status codes into error categories.

    Args:
        status_code: HTTP status code

    Returns:
        ErrorCategoryEnum for the given status code
    """
    # Guard: handle 404 explicitly
    if status_code == 404:
        return ErrorCategoryEnum.NOT_FOUND

    # Guard: handle authentication/authorization
    if status_code in (401, 403):
        return ErrorCategoryEnum.AUTH_ERROR

    # Guard: handle rate limiting
    if status_code == 429:
        return ErrorCategoryEnum.RATE_LIMIT

    # Guard: handle client errors (4xx except handled above)
    if 400 <= status_code < 500:
        return ErrorCategoryEnum.CLIENT_ERROR

    # Guard: handle server errors (5xx)
    if 500 <= status_code < 600:
        return ErrorCategoryEnum.SERVER_ERROR

    # All other status codes are unknown
    return ErrorCategoryEnum.UNKNOWN


def classify_exception(exc: Exception) -> ErrorCategoryEnum:
    """Classify Python exceptions into error categories.

    Args:
        exc: The exception to classify

    Returns:
        ErrorCategoryEnum for the given exception
    """
    exc_type_name = type(exc).__name__
    exc_module = type(exc).__module__

    # Timeout errors (separate from network for different retry policy)
    if exc_type_name in ("TimeoutError", "ConnectTimeout", "ReadTimeout"):
        return ErrorCategoryEnum.TIMEOUT

    # Network errors (connection, DNS, SSL issues)
    if exc_type_name in (
        "ConnectionError",
        "DNSError",
        "SSLError",
        "ConnectionRefusedError",
        "ConnectionResetError",
    ):
        return ErrorCategoryEnum.NETWORK

    # Specific httpx network errors
    if exc_module == "httpx" and exc_type_name in (
        "ConnectError",
        "ReadError",
        "WriteError",
        "PoolTimeout",
        "ProtocolError",
    ):
        return ErrorCategoryEnum.NETWORK

    # Browser crash errors
    if exc_type_name == "BrowserCrashError":
        return ErrorCategoryEnum.BROWSER_CRASH

    # Playwright/Selenium errors that indicate browser issues
    if exc_type_name in (
        "TargetClosedError",
        "BrowserContextClosedError",
        "PageClosedError",
    ):
        return ErrorCategoryEnum.BROWSER_CRASH

    # Timeout errors (asyncio, page load, selector wait)
    if "timeout" in exc_type_name.lower() or "TimeoutException" in exc_type_name:
        return ErrorCategoryEnum.TIMEOUT

    # Validation errors (config, input, step validation)
    if exc_type_name in ("StepValidationError", "ValidationError", "ValueError"):
        return ErrorCategoryEnum.VALIDATION_ERROR

    # Resource exhaustion (memory, disk, connections)
    if exc_type_name in ("MemoryError", "ResourceWarning", "OSError"):
        # Check if OSError is due to file descriptors or disk space
        if isinstance(exc, OSError):
            # errno 24: Too many open files
            # errno 28: No space left on device
            if exc.errno in (24, 28):
                return ErrorCategoryEnum.RESOURCE_UNAVAILABLE
        return ErrorCategoryEnum.RESOURCE_UNAVAILABLE

    # Unknown error type
    return ErrorCategoryEnum.UNKNOWN


def get_error_context(exc: Exception) -> dict[str, str]:
    """Extract error context from exception for logging.

    Args:
        exc: The exception to extract context from

    Returns:
        Dictionary with error details
    """
    return {
        "exception_type": type(exc).__name__,
        "exception_module": type(exc).__module__,
        "error_message": str(exc),
        "stack_trace": "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)),
    }


# ============================================================================
# Jitter and Retry-After Header Support
# ============================================================================


def add_jitter(delay: int, jitter_percent: float = 0.2) -> int:
    """Add random jitter to delay to avoid thundering herd problem.

    Args:
        delay: Base delay in seconds
        jitter_percent: Percentage of jitter (0.0-1.0), default 0.2 (20%)

    Returns:
        Delay with jitter applied, as integer seconds

    Examples:
        >>> random.seed(42)
        >>> add_jitter(10, 0.2)  # Will add 0-20% jitter
        11
        >>> add_jitter(100, 0.1)  # Will add 0-10% jitter
        105
    """
    # Guard: ensure jitter_percent is valid
    if jitter_percent < 0 or jitter_percent > 1:
        logger.warning("invalid_jitter_percent", jitter_percent=jitter_percent)
        jitter_percent = 0.2

    # Calculate jitter range: delay ± (delay * jitter_percent)
    jitter_amount = int(delay * jitter_percent)
    jittered_delay = delay + random.randint(-jitter_amount, jitter_amount)

    # Guard: ensure delay is never negative
    return max(0, jittered_delay)


def parse_retry_after_header(retry_after: str | None) -> int | None:
    """Parse Retry-After header from HTTP response.

    Supports two formats:
    1. Delay-seconds: "120" (wait 120 seconds)
    2. HTTP-date: "Wed, 21 Oct 2025 07:28:00 GMT"

    Args:
        retry_after: Value of Retry-After header

    Returns:
        Delay in seconds, or None if header is invalid/missing

    Examples:
        >>> parse_retry_after_header("120")
        120
        >>> parse_retry_after_header("Wed, 21 Oct 2025 07:28:00 GMT")  # depends on current time
        # Returns seconds until that date
        >>> parse_retry_after_header(None)
        None
        >>> parse_retry_after_header("invalid")
        None
    """
    # Guard: no header provided
    if not retry_after:
        return None

    # Try parsing as integer (delay-seconds format)
    try:
        return int(retry_after)
    except ValueError:
        pass  # Fall through to HTTP-date parsing

    # Try parsing as HTTP-date format
    try:
        retry_datetime = parsedate_to_datetime(retry_after)
        now = datetime.now(UTC)

        # Calculate seconds until retry_datetime
        delta = (retry_datetime - now).total_seconds()

        # Guard: if date is in the past, return 0
        return max(0, int(delta))
    except (ValueError, TypeError, OverflowError) as e:
        logger.warning("invalid_retry_after_header", retry_after=retry_after, error=str(e))
        return None


# ============================================================================
# Backoff Calculation
# ============================================================================


def calculate_exponential_backoff(
    attempt: int, initial_delay: int, max_delay: int, multiplier: float
) -> int:
    """Calculate exponential backoff delay.

    Formula: delay = min(initial_delay * (base ^ (attempt - 1)), max_delay)
    Note: Uses (attempt - 1) so first retry (attempt=1) gets initial_delay * base^0 = initial_delay

    Args:
        attempt: Current attempt number (1-indexed: 1, 2, 3, ...)
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds (cap)
        multiplier: Base for exponential growth

    Returns:
        Delay in seconds, capped at max_delay

    Examples:
        >>> calculate_exponential_backoff(1, 1, 300, 2.0)  # First retry
        1
        >>> calculate_exponential_backoff(2, 1, 300, 2.0)  # Second retry
        2
        >>> calculate_exponential_backoff(3, 1, 300, 2.0)  # Third retry
        4
        >>> calculate_exponential_backoff(11, 1, 300, 2.0)  # Capped at max
        300
    """
    # Use (attempt - 1) so first retry gets base^0 = 1x initial_delay
    delay = initial_delay * (multiplier ** (attempt - 1))
    return min(int(delay), max_delay)


def calculate_linear_backoff(
    attempt: int, initial_delay: int, max_delay: int, multiplier: float
) -> int:
    """Calculate linear backoff delay.

    Formula: delay = min(initial_delay + (multiplier * (attempt - 1)), max_delay)

    Args:
        attempt: Current attempt number (1-indexed: 1, 2, 3, ...)
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds (cap)
        multiplier: Multiplier for linear growth

    Returns:
        Delay in seconds, capped at max_delay

    Examples:
        >>> calculate_linear_backoff(1, 5, 60, 1.5)
        5
        >>> calculate_linear_backoff(2, 5, 60, 1.5)
        6
        >>> calculate_linear_backoff(50, 5, 60, 1.5)
        60
    """
    delay = initial_delay + (multiplier * (attempt - 1))
    return min(int(delay), max_delay)


def calculate_fixed_backoff(initial_delay: int, max_delay: int) -> int:
    """Calculate fixed backoff delay.

    Always returns the same delay (initial_delay), capped at max_delay.

    Args:
        initial_delay: Delay in seconds
        max_delay: Maximum delay in seconds (cap)

    Returns:
        Delay in seconds

    Examples:
        >>> calculate_fixed_backoff(10, 60)
        10
        >>> calculate_fixed_backoff(100, 60)
        60
    """
    return min(initial_delay, max_delay)


def calculate_backoff(
    strategy: BackoffStrategyEnum,
    attempt: int,
    initial_delay: int,
    max_delay: int,
    multiplier: float,
    *,
    apply_jitter: bool = False,
    jitter_percent: float = 0.2,
    retry_after: str | None = None,
) -> int:
    """Calculate backoff delay based on strategy with optional jitter and Retry-After.

    Args:
        strategy: Backoff strategy (exponential/linear/fixed)
        attempt: Current attempt number (1-indexed)
        initial_delay: Initial delay in seconds
        max_delay: Maximum delay in seconds (cap at 300s)
        multiplier: Multiplier for backoff calculation
        apply_jitter: Whether to add random jitter (default: False)
        jitter_percent: Jitter percentage 0.0-1.0 (default: 0.2 = 20%)
        retry_after: Optional Retry-After header value

    Returns:
        Delay in seconds, capped at max_delay (300s max)

    Raises:
        ValueError: If strategy is unknown

    Examples:
        >>> random.seed(42)
        >>> calculate_backoff(BackoffStrategyEnum.EXPONENTIAL, 2, 1, 300, 2.0)
        2
        >>> calculate_backoff(BackoffStrategyEnum.EXPONENTIAL, 2, 1, 300, 2.0, apply_jitter=True)
        2  # With jitter
        >>> calculate_backoff(BackoffStrategyEnum.EXPONENTIAL, 1, 1, 300, 2.0, retry_after="60")
        60  # Respects Retry-After
    """
    # Guard: Retry-After takes precedence over calculated delay
    if retry_after:
        retry_delay = parse_retry_after_header(retry_after)
        if retry_delay is not None:
            logger.info(
                "using_retry_after_header",
                retry_after=retry_after,
                delay_seconds=retry_delay,
            )
            # Still cap at max_delay even for Retry-After
            return min(retry_delay, max_delay)

    # Calculate base delay using strategy
    if strategy == BackoffStrategyEnum.EXPONENTIAL:
        delay = calculate_exponential_backoff(attempt, initial_delay, max_delay, multiplier)
    elif strategy == BackoffStrategyEnum.LINEAR:
        delay = calculate_linear_backoff(attempt, initial_delay, max_delay, multiplier)
    elif strategy == BackoffStrategyEnum.FIXED:
        delay = calculate_fixed_backoff(initial_delay, max_delay)
    else:
        raise ValueError(f"Unknown backoff strategy: {strategy}")

    # Apply jitter if requested
    if apply_jitter:
        delay = add_jitter(delay, jitter_percent)

    # Final cap at max_delay (300s absolute maximum)
    return min(delay, max_delay, 300)


# ============================================================================
# Retry Policy Service
# ============================================================================


class RetryPolicyService:
    """Service for retry policy management and error classification."""

    def __init__(self, retry_policy_repo: RetryPolicyRepository):
        """Initialize retry policy service.

        Args:
            retry_policy_repo: Repository for retry policy operations
        """
        self.retry_policy_repo = retry_policy_repo

    async def get_policy_for_error(
        self, exc: Exception | None = None, http_status: int | None = None
    ) -> tuple[ErrorCategoryEnum, bool, int, int]:
        """Get retry policy for an error.

        Args:
            exc: Optional exception to classify
            http_status: Optional HTTP status code

        Returns:
            Tuple of (error_category, is_retryable, max_attempts, calculated_delay)
        """
        # Classify error
        if http_status is not None:
            error_category = classify_http_status(http_status)
        elif exc is not None:
            error_category = classify_exception(exc)
        else:
            error_category = ErrorCategoryEnum.UNKNOWN

        # Get policy from database
        policy = await self.retry_policy_repo.get_by_category(error_category)

        # Guard: policy not found (shouldn't happen with seed data, but be defensive)
        if not policy:
            logger.warning("retry_policy_not_found", error_category=error_category)
            return (error_category, False, 0, 0)

        # Calculate initial delay for first retry (attempt 1)
        delay = calculate_backoff(
            strategy=policy.backoff_strategy,
            attempt=1,
            initial_delay=policy.initial_delay_seconds,
            max_delay=policy.max_delay_seconds,
            multiplier=policy.backoff_multiplier,
        )

        return (error_category, policy.is_retryable, policy.max_attempts, delay)

    async def calculate_next_delay(
        self, error_category: ErrorCategoryEnum, attempt_number: int
    ) -> int:
        """Calculate delay for the next retry attempt.

        Args:
            error_category: Category of the error
            attempt_number: Current attempt number (1-indexed)

        Returns:
            Delay in seconds before next retry
        """
        policy = await self.retry_policy_repo.get_by_category(error_category)

        # Guard: policy not found
        if not policy:
            logger.warning("retry_policy_not_found_for_delay", error_category=error_category)
            return 10  # Default fallback: 10 seconds

        return calculate_backoff(
            strategy=policy.backoff_strategy,
            attempt=attempt_number,
            initial_delay=policy.initial_delay_seconds,
            max_delay=policy.max_delay_seconds,
            multiplier=policy.backoff_multiplier,
        )
