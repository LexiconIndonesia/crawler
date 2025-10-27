"""Cron utilities for scheduled job management."""

from datetime import datetime

from croniter import croniter


def calculate_next_run(cron_expression: str, base_time: datetime | None = None) -> datetime:
    """Calculate the next run time for a cron expression.

    Args:
        cron_expression: Valid cron expression (e.g., '0 0 * * *')
        base_time: Base time to calculate from (defaults to current UTC time)

    Returns:
        Next scheduled execution time (timezone-aware UTC)

    Raises:
        ValueError: If the cron expression is invalid

    Example:
        >>> from datetime import datetime, UTC
        >>> next_run = calculate_next_run("0 0 * * *")  # Next midnight
        >>> next_run = calculate_next_run("0 0 1,15 * *")  # Next 1st or 15th
    """
    from datetime import UTC

    if base_time is None:
        base_time = datetime.now(UTC)

    cron = croniter(cron_expression, base_time)
    next_time = cron.get_next(datetime)

    # Ensure timezone-aware datetime
    if next_time.tzinfo is None:
        next_time = next_time.replace(tzinfo=UTC)

    return next_time


def is_valid_cron(cron_expression: str) -> bool:
    """Check if a cron expression is valid.

    Args:
        cron_expression: Cron expression to validate

    Returns:
        True if valid, False otherwise

    Example:
        >>> is_valid_cron("0 0 * * *")
        True
        >>> is_valid_cron("invalid")
        False
    """
    try:
        croniter(cron_expression)
        return True
    except (ValueError, KeyError):
        return False
