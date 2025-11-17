"""Validation utilities for API requests."""

import re
from datetime import datetime

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
        >>> validate_cron_expression("@annually")
        (True, None)
        >>> validate_cron_expression("invalid")
        (False, "Invalid cron expression format...")
    """
    # Check for extended syntax first (@yearly, @annually, @daily, etc.)
    extended_syntax = [
        "@yearly",
        "@annually",  # Alias for @yearly
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
    timezone: str = "UTC",
) -> datetime:
    """Calculate the next run time for a cron expression in user's timezone.

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).
    Calculates next run time in the specified timezone, then converts to UTC for storage.

    Args:
        cron_expression: Valid cron expression or extended syntax
            - Standard: "0 0 * * *" (daily at midnight)
            - Extended: "@daily", "@weekly", "@hourly", etc.
        base_time: Base time to calculate from (defaults to now in UTC)
            Must be timezone-aware. If naive, assumes UTC.
        timezone: IANA timezone name for schedule calculations
            (e.g., "UTC", "America/New_York", "Asia/Jakarta")

    Returns:
        Next scheduled run time in UTC (always timezone-aware)

    Raises:
        ValueError: If cron expression or timezone is invalid

    Examples:
        >>> # Next occurrence of "0 0 1,15 * *" (midnight on 1st or 15th) in UTC
        >>> next_run = calculate_next_run_time("0 0 1,15 * *")
        >>> isinstance(next_run, datetime)
        True
        >>> # Next 2 AM Jakarta time (returns UTC time)
        >>> next_run = calculate_next_run_time("0 2 * * *", timezone="Asia/Jakarta")
        >>> isinstance(next_run, datetime)
        True
    """
    from crawler.utils.cron import calculate_next_run

    # Delegate to the cron utility which handles timezone conversion
    return calculate_next_run(cron_expression, base_time, timezone)


def validate_and_calculate_next_run(
    cron_expression: str,
    base_time: datetime | None = None,
    timezone: str = "UTC",
) -> tuple[bool, str | datetime]:
    """Validate cron expression and calculate next run time in user's timezone.

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).
    Calculates next run time in the specified timezone, then converts to UTC for storage.

    Args:
        cron_expression: Cron expression to validate
            - Standard: "0 0 * * *" (daily at midnight)
            - Extended: "@daily", "@weekly", "@hourly", etc.
        base_time: Base time for calculation (defaults to now in UTC)
            Must be timezone-aware. If naive, assumes UTC.
        timezone: IANA timezone name for schedule calculations
            (e.g., "UTC", "America/New_York", "Asia/Jakarta")

    Returns:
        Tuple of (is_valid, error_message_or_next_run_time)
        If is_valid is True, returns (True, next_run_datetime_utc)
        If is_valid is False, returns (False, error_message_string)

    Examples:
        >>> valid, result = validate_and_calculate_next_run("0 0 1,15 * *")
        >>> valid
        True
        >>> isinstance(result, datetime)
        True
        >>> # Calculate next 2 AM Jakarta time (returns UTC)
        >>> valid, result = validate_and_calculate_next_run("0 2 * * *", timezone="Asia/Jakarta")
        >>> valid
        True
    """
    is_valid, error_message = validate_cron_expression(cron_expression)
    if not is_valid:
        return False, error_message  # type: ignore[return-value]

    try:
        next_run = calculate_next_run_time(cron_expression, base_time, timezone)
        return True, next_run
    except ValueError as e:
        return False, str(e)  # type: ignore[return-value]
