"""Cron utilities for scheduled job management."""

from datetime import datetime

from croniter import croniter


def calculate_next_run(
    cron_expression: str,
    base_time: datetime | None = None,
) -> datetime:
    """Calculate the next run time for a cron expression.

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).

    Args:
        cron_expression: Valid cron expression or extended syntax
            - Standard: "0 0 * * *" (daily at midnight)
            - Extended: "@daily", "@weekly", "@hourly", etc.
        base_time: Base time to calculate from (defaults to current UTC time)
            Must be timezone-aware. If naive, assumes UTC.

    Returns:
        Next scheduled execution time (always timezone-aware in UTC)

    Raises:
        ValueError: If the cron expression is invalid

    Example:
        >>> from datetime import datetime, UTC
        >>> next_run = calculate_next_run("0 0 * * *")  # Next midnight
        >>> next_run = calculate_next_run("0 0 1,15 * *")  # Next 1st or 15th
        >>> next_run = calculate_next_run("@daily")  # Next midnight (extended syntax)
    """
    from datetime import UTC

    if base_time is None:
        base_time = datetime.now(UTC)
    elif base_time.tzinfo is None:
        # If naive datetime provided, assume UTC
        base_time = base_time.replace(tzinfo=UTC)

    try:
        cron = croniter(cron_expression, base_time)
        next_time = cron.get_next(datetime)

        # Ensure timezone-aware datetime
        if next_time.tzinfo is None:
            next_time = next_time.replace(tzinfo=UTC)

        return next_time
    except (ValueError, KeyError) as e:
        raise ValueError(f"Invalid cron expression '{cron_expression}': {str(e)}") from e


def is_valid_cron(cron_expression: str) -> bool:
    """Check if a cron expression is valid.

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).

    Args:
        cron_expression: Cron expression to validate
            - Standard: "0 0 * * *" (daily at midnight)
            - Extended: "@daily", "@weekly", "@hourly", "@yearly", "@monthly", "@midnight"

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_cron("0 0 * * *")
        True
        >>> is_valid_cron("@daily")
        True
        >>> is_valid_cron("invalid")
        False
    """
    try:
        croniter(cron_expression)
        return True
    except (ValueError, KeyError):
        return False
