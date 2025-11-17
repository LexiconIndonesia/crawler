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
from collections.abc import Callable
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


def classify_http_status(status_code: int, *, log_decision: bool = True) -> ErrorCategoryEnum:
    """Classify HTTP status codes into error categories.

    Args:
        status_code: HTTP status code
        log_decision: Whether to log the classification decision (default: True)

    Returns:
        ErrorCategoryEnum for the given status code
    """
    # Guard: handle 404 explicitly
    if status_code == 404:
        category = ErrorCategoryEnum.NOT_FOUND
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="http_status",
                status_code=status_code,
                error_category=category.value,
                is_retryable=False,
                reason="404 Not Found is a permanent error",
            )
        return category

    # Guard: handle authentication/authorization
    if status_code in (401, 403):
        category = ErrorCategoryEnum.AUTH_ERROR
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="http_status",
                status_code=status_code,
                error_category=category.value,
                is_retryable=False,
                reason="Authentication/authorization errors are typically permanent",
            )
        return category

    # Guard: handle rate limiting
    if status_code == 429:
        category = ErrorCategoryEnum.RATE_LIMIT
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="http_status",
                status_code=status_code,
                error_category=category.value,
                is_retryable=True,
                reason="Rate limit errors should be retried with backoff",
            )
        return category

    # Guard: handle request timeout (408)
    # Note: 408 is treated as a timeout-style retryable error (similar to network/server timeouts)
    # rather than a permanent client error, since it typically indicates transient conditions
    if status_code == 408:
        category = ErrorCategoryEnum.TIMEOUT
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="http_status",
                status_code=status_code,
                error_category=category.value,
                is_retryable=True,
                reason="HTTP 408 Request Timeout is transient and retryable",
            )
        return category

    # Guard: handle client errors (4xx except handled above)
    if 400 <= status_code < 500:
        category = ErrorCategoryEnum.CLIENT_ERROR
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="http_status",
                status_code=status_code,
                error_category=category.value,
                is_retryable=False,
                reason="Client errors (4xx) are typically permanent",
            )
        return category

    # Guard: handle server errors (5xx)
    if 500 <= status_code < 600:
        category = ErrorCategoryEnum.SERVER_ERROR
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="http_status",
                status_code=status_code,
                error_category=category.value,
                is_retryable=True,
                reason="Server errors (5xx) are typically transient and retryable",
            )
        return category

    # All other status codes are unknown
    category = ErrorCategoryEnum.UNKNOWN
    if log_decision:
        logger.warning(
            "error_classified_as_unknown",
            classification_type="http_status",
            status_code=status_code,
            error_category=category.value,
            is_retryable=False,
            reason="Unexpected status code outside standard HTTP ranges",
        )
    return category


def classify_exception(exc: Exception, *, log_decision: bool = True) -> ErrorCategoryEnum:
    """Classify Python exceptions into error categories.

    Args:
        exc: The exception to classify
        log_decision: Whether to log the classification decision (default: True)

    Returns:
        ErrorCategoryEnum for the given exception
    """
    exc_type_name = type(exc).__name__
    exc_module = type(exc).__module__

    # Timeout errors (separate from network for different retry policy)
    if exc_type_name in ("TimeoutError", "ConnectTimeout", "ReadTimeout"):
        category = ErrorCategoryEnum.TIMEOUT
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=True,
                reason="Timeout errors are typically transient and retryable",
            )
        return category

    # Network errors (connection, DNS, SSL issues)
    if exc_type_name in (
        "ConnectionError",
        "DNSError",
        "SSLError",
        "ConnectionRefusedError",
        "ConnectionResetError",
    ):
        category = ErrorCategoryEnum.NETWORK
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=True,
                reason="Network errors are typically transient and retryable",
            )
        return category

    # Specific httpx network errors
    if exc_module == "httpx" and exc_type_name in (
        "ConnectError",
        "ReadError",
        "WriteError",
        "PoolTimeout",
        "ProtocolError",
    ):
        category = ErrorCategoryEnum.NETWORK
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=True,
                reason="httpx network errors are typically transient and retryable",
            )
        return category

    # Browser crash errors
    if exc_type_name == "BrowserCrashError":
        category = ErrorCategoryEnum.BROWSER_CRASH
        if log_decision:
            logger.warning(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=True,
                reason="Browser crash detected - will retry with fresh browser instance",
            )
        return category

    # Playwright/Selenium errors that indicate browser issues
    if exc_type_name in (
        "TargetClosedError",
        "BrowserContextClosedError",
        "PageClosedError",
    ):
        category = ErrorCategoryEnum.BROWSER_CRASH
        if log_decision:
            logger.warning(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=True,
                reason="Browser context/page closed unexpectedly - indicates crash",
            )
        return category

    # Timeout errors (asyncio, page load, selector wait)
    # Note: This heuristic catches common timeout exceptions by name substring matching
    # (e.g., asyncio.TimeoutError, PlaywrightTimeoutError, etc.)
    # If this catches unrelated exceptions, add explicit checks above or use custom rules
    if "timeout" in exc_type_name.lower() or "TimeoutException" in exc_type_name:
        category = ErrorCategoryEnum.TIMEOUT
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=True,
                reason="Timeout errors are typically transient and retryable",
            )
        return category

    # Validation errors (config, input, step validation)
    if exc_type_name in ("StepValidationError", "ValidationError", "ValueError"):
        category = ErrorCategoryEnum.VALIDATION_ERROR
        if log_decision:
            logger.info(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=False,
                reason="Validation errors indicate permanent configuration/input issues",
            )
        return category

    # Resource exhaustion (memory, disk, connections)
    if exc_type_name in ("MemoryError", "ResourceWarning", "OSError"):
        # Check if OSError is due to file descriptors or disk space
        if isinstance(exc, OSError):
            # errno 24: Too many open files
            # errno 28: No space left on device
            if exc.errno in (24, 28):
                category = ErrorCategoryEnum.RESOURCE_UNAVAILABLE
                if log_decision:
                    logger.warning(
                        "error_classified",
                        classification_type="exception",
                        exception_type=exc_type_name,
                        exception_module=exc_module,
                        error_category=category.value,
                        is_retryable=True,
                        os_errno=exc.errno,
                        reason=f"Resource exhaustion (errno {exc.errno}) - may resolve with retry",
                    )
                return category
        category = ErrorCategoryEnum.RESOURCE_UNAVAILABLE
        if log_decision:
            logger.warning(
                "error_classified",
                classification_type="exception",
                exception_type=exc_type_name,
                exception_module=exc_module,
                error_category=category.value,
                is_retryable=True,
                reason="Resource exhaustion - may resolve with retry and cleanup",
            )
        return category

    # Unknown error type
    # Note: We conservatively mark UNKNOWN exceptions as non-retryable (is_retryable=False)
    # to avoid infinite retry loops on unexpected errors. If your retry policy is managed
    # via database policies or custom rules, those can override this classification.
    # To make specific unknown exceptions retryable, add them to the explicit checks above
    # or use ErrorClassificationRule with custom predicates.
    category = ErrorCategoryEnum.UNKNOWN
    if log_decision:
        logger.warning(
            "error_classified_as_unknown",
            classification_type="exception",
            exception_type=exc_type_name,
            exception_module=exc_module,
            error_category=category.value,
            is_retryable=False,
            error_message=str(exc),
            reason="Exception type not recognized - treating conservatively as permanent",
        )
    return category


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
# Custom Classification Rules
# ============================================================================


class ErrorClassificationRule:
    """Custom rule for classifying errors.

    Rules are evaluated in order and the first matching rule wins.
    Each rule has a predicate function that determines if it matches
    and a target category to return when it matches.
    """

    def __init__(
        self,
        name: str,
        predicate: Callable[[Exception | None, int | None], bool],
        category: ErrorCategoryEnum,
        reason: str,
        is_retryable: bool | None = None,
    ):
        """Initialize classification rule.

        Args:
            name: Human-readable name for the rule
            predicate: Function that takes (exc, status_code) and returns bool
            category: ErrorCategoryEnum to return when rule matches
            reason: Explanation of why this rule matches (for logging)
            is_retryable: Optional override for retryability. If None, no override is applied
                and the caller (e.g., DB policy or higher-level logic) uses its own defaults

        Raises:
            ValueError: If name is empty, predicate is None/not callable, or reason is empty
        """
        # Guard: validate name
        if not name:
            raise ValueError("Rule name cannot be empty")

        # Guard: validate predicate
        if predicate is None:
            raise ValueError("Rule predicate cannot be None")
        if not callable(predicate):
            raise ValueError("Rule predicate must be callable")

        # Guard: validate reason
        if not reason:
            raise ValueError("Rule reason cannot be empty")

        self.name = name
        self.predicate = predicate
        self.category = category
        self.reason = reason
        self.is_retryable = is_retryable


def classify_with_custom_rules(
    exc: Exception | None = None,
    http_status: int | None = None,
    custom_rules: list[ErrorClassificationRule] | None = None,
    *,
    log_decision: bool = True,
) -> tuple[ErrorCategoryEnum, bool | None]:
    """Classify error with optional custom rules.

    Custom rules are evaluated first, then falls back to standard classification.

    Precedence when both exc and http_status are provided:
        1. Custom rules (evaluated first, can match on either/both)
        2. HTTP status classification (if no custom rule matches)
        3. Exception classification (if no http_status provided)

    Args:
        exc: Optional exception to classify
        http_status: Optional HTTP status code
        custom_rules: List of custom classification rules to try first
        log_decision: Whether to log the classification decision (default: True)

    Returns:
        Tuple of (error_category, is_retryable_override).
        is_retryable_override is None if using category default, or bool if custom rule overrides.

    Examples:
        >>> # Create custom rule for domain-specific errors
        >>> def is_rate_limit_error(exc, status_code):
        ...     # Custom logic: check if error message contains rate limit keywords
        ...     if exc and "rate" in str(exc).lower() and "limit" in str(exc).lower():
        ...         return True
        ...     return False
        >>> rule = ErrorClassificationRule(
        ...     name="custom_rate_limit_detection",
        ...     predicate=is_rate_limit_error,
        ...     category=ErrorCategoryEnum.RATE_LIMIT,
        ...     reason="Custom rate limit detection via error message keywords",
        ...     is_retryable=True,
        ... )
        >>> category, is_retryable = classify_with_custom_rules(
        ...     exc=Exception("API rate limit exceeded"),
        ...     custom_rules=[rule]
        ... )
        >>> # category = ErrorCategoryEnum.RATE_LIMIT, is_retryable = True
    """
    # Try custom rules first (in order)
    if custom_rules:
        for rule in custom_rules:
            try:
                if rule.predicate(exc, http_status):
                    if log_decision:
                        logger.info(
                            "error_classified_custom_rule",
                            classification_type="custom_rule",
                            rule_name=rule.name,
                            error_category=rule.category.value,
                            is_retryable=rule.is_retryable,
                            reason=rule.reason,
                            exception_type=type(exc).__name__ if exc else None,
                            status_code=http_status,
                        )
                    # Return category and retryable override (may be None)
                    return (rule.category, rule.is_retryable)
            except Exception as e:
                # Guard: if custom rule raises exception, log and skip it
                # Use getattr for defensive access in case non-ErrorClassificationRule object passed
                logger.error(
                    "custom_rule_error",
                    rule_name=getattr(rule, "name", "<unknown>"),
                    error=str(e),
                    reason="Custom classification rule raised exception - skipping",
                )
                continue

    # Fall back to standard classification (no override)
    if http_status is not None:
        return (classify_http_status(http_status, log_decision=log_decision), None)

    if exc is not None:
        return (classify_exception(exc, log_decision=log_decision), None)

    # No error provided - return UNKNOWN (no override)
    category = ErrorCategoryEnum.UNKNOWN
    if log_decision:
        logger.warning(
            "error_classified_as_unknown",
            classification_type="no_error_provided",
            error_category=category.value,
            reason="No exception or HTTP status provided for classification",
        )
    return (category, None)


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
