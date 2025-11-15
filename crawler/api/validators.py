"""Validation utilities for API requests."""

import re
from datetime import UTC, datetime

from croniter import croniter


def validate_cron_expression(cron_expression: str) -> tuple[bool, str | None]:
    """Validate a cron expression format.

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).

    Args:
        cron_expression: Cron expression string
            - Standard: 5 or 6 fields (minute hour day month weekday [second])
            - Extended: @yearly, @annually, @monthly, @weekly, @daily, @midnight, @hourly

    Returns:
        Tuple of (is_valid, error_message)

    Examples:
        >>> validate_cron_expression("0 0 1,15 * *")
        (True, None)
        >>> validate_cron_expression("@daily")
        (True, None)
        >>> validate_cron_expression("invalid")
        (False, "Invalid cron expression format...")
    """
    # Check for extended syntax first (@yearly, @daily, etc.)
    extended_syntax = [
        "@yearly",
        "@annually",
        "@monthly",
        "@weekly",
        "@daily",
        "@midnight",
        "@hourly",
    ]
    if cron_expression in extended_syntax:
        # Extended syntax is always valid, let croniter handle it
        try:
            croniter(cron_expression)
            return True, None
        except (ValueError, KeyError) as e:
            return False, f"Invalid cron expression: {str(e)}"

    # Basic format check: 5 or 6 fields separated by spaces
    # Pattern supports: *, numbers, ranges (1-5), lists (1,3,5), steps (*/5, 1-10/2)
    cron_field = r"(\*(/[0-9]+)?|[0-9,\-/]+|[A-Z]{3})"
    cron_pattern = (
        rf"^{cron_field}\s+{cron_field}\s+{cron_field}\s+"
        rf"{cron_field}\s+{cron_field}(\s+{cron_field})?$"
    )

    if not re.match(cron_pattern, cron_expression):
        return (
            False,
            "Invalid cron expression format. Expected: 'minute hour day month weekday' "
            "(e.g., '0 0 1,15 * *') or extended syntax (e.g., '@daily', '@weekly')",
        )

    # Validate using croniter for deeper validation
    try:
        croniter(cron_expression)
        return True, None
    except (ValueError, KeyError) as e:
        return False, f"Invalid cron expression: {str(e)}"


def calculate_next_run_time(
    cron_expression: str,
    base_time: datetime | None = None,
) -> datetime:
    """Calculate the next run time for a cron expression.

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).

    Args:
        cron_expression: Valid cron expression or extended syntax
            - Standard: "0 0 * * *" (daily at midnight)
            - Extended: "@daily", "@weekly", "@hourly", etc.
        base_time: Base time to calculate from (defaults to now in UTC)
            Must be timezone-aware. If naive, assumes UTC.

    Returns:
        Next scheduled run time (always timezone-aware in UTC)

    Raises:
        ValueError: If cron expression is invalid

    Examples:
        >>> # Next occurrence of "0 0 1,15 * *" (midnight on 1st or 15th)
        >>> next_run = calculate_next_run_time("0 0 1,15 * *")
        >>> isinstance(next_run, datetime)
        True
        >>> # Using extended syntax
        >>> next_run = calculate_next_run_time("@daily")
        >>> isinstance(next_run, datetime)
        True
    """
    if base_time is None:
        base_time = datetime.now(UTC)
    elif base_time.tzinfo is None:
        # If naive datetime provided, assume UTC
        base_time = base_time.replace(tzinfo=UTC)

    try:
        cron = croniter(cron_expression, base_time)
        next_time = cron.get_next(datetime)
        # Ensure timezone-aware datetime in UTC
        if next_time.tzinfo is None:
            next_time = next_time.replace(tzinfo=UTC)
        return next_time
    except (ValueError, KeyError) as e:
        raise ValueError(f"Invalid cron expression '{cron_expression}': {str(e)}") from e


def validate_and_calculate_next_run(
    cron_expression: str,
    base_time: datetime | None = None,
) -> tuple[bool, str | datetime]:
    """Validate cron expression and calculate next run time.

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).

    Args:
        cron_expression: Cron expression to validate
            - Standard: "0 0 * * *" (daily at midnight)
            - Extended: "@daily", "@weekly", "@hourly", etc.
        base_time: Base time for calculation (defaults to now in UTC)
            Must be timezone-aware. If naive, assumes UTC.

    Returns:
        Tuple of (is_valid, error_message_or_next_run_time)
        If is_valid is True, returns (True, next_run_datetime)
        If is_valid is False, returns (False, error_message_string)

    Examples:
        >>> valid, result = validate_and_calculate_next_run("0 0 1,15 * *")
        >>> valid
        True
        >>> isinstance(result, datetime)
        True
        >>> valid, result = validate_and_calculate_next_run("@daily")
        >>> valid
        True
        >>> isinstance(result, datetime)
        True
    """
    is_valid, error_message = validate_cron_expression(cron_expression)
    if not is_valid:
        return False, error_message  # type: ignore[return-value]

    try:
        next_run = calculate_next_run_time(cron_expression, base_time)
        return True, next_run
    except ValueError as e:
        return False, str(e)  # type: ignore[return-value]
