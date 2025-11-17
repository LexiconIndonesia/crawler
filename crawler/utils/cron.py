"""Cron utilities for scheduled job management with timezone support."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from croniter import croniter


def calculate_next_run(
    cron_expression: str,
    base_time: datetime | None = None,
    timezone: str = "UTC",
) -> datetime:
    """Calculate the next run time for a cron expression in the user's timezone.

    This function calculates the next run time in the specified timezone (e.g., Jakarta time),
    then converts it to UTC for storage. This ensures schedules honor the user's local timezone.

    For example, "0 2 * * *" with timezone="Asia/Jakarta" means 2 AM Jakarta time every day,
    which will be converted to UTC for storage (e.g., 7 PM UTC the previous day when
    Jakarta is UTC+7).

    Supports both standard cron syntax and extended syntax (@daily, @weekly, etc.).

    Args:
        cron_expression: Valid cron expression or extended syntax
            - Standard: "0 0 * * *" (daily at midnight)
            - Extended: "@daily", "@weekly", "@hourly", etc.
        base_time: Base time to calculate from (defaults to current UTC time)
            Must be timezone-aware. If naive, assumes UTC.
        timezone: IANA timezone name for schedule calculations
            (e.g., "Asia/Jakarta", "America/New_York"). The cron expression will be
            evaluated in this timezone, then converted to UTC.

    Returns:
        Next scheduled execution time in UTC (always timezone-aware)

    Raises:
        ValueError: If the cron expression or timezone is invalid

    Example:
        >>> from datetime import datetime, UTC
        >>> # Calculate next 2 AM Jakarta time (returns UTC time)
        >>> next_run = calculate_next_run("0 2 * * *", timezone="Asia/Jakarta")
        >>> # For Jakarta (UTC+7), 2 AM local = 7 PM previous day UTC
        >>> next_run = calculate_next_run("@daily", timezone="UTC")  # Standard UTC
    """
    # Guard: default to now in UTC if no base time provided
    if base_time is None:
        base_time = datetime.now(UTC)
    elif base_time.tzinfo is None:
        # If naive datetime provided, assume UTC
        base_time = base_time.replace(tzinfo=UTC)

    try:
        # Convert base time to the target timezone for cron calculation
        tz = ZoneInfo(timezone)
        base_time_local = base_time.astimezone(tz)

        # Calculate next run time in the target timezone
        cron = croniter(cron_expression, base_time_local)
        next_time_local = cron.get_next(datetime)

        # Ensure timezone-aware datetime in target timezone
        if next_time_local.tzinfo is None:
            next_time_local = next_time_local.replace(tzinfo=tz)

        # Convert back to UTC for storage
        next_time_utc = next_time_local.astimezone(UTC)

        return next_time_utc
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
