"""DST (Daylight Saving Time) utilities for scheduling.

This module provides utilities for handling DST transitions in scheduled jobs.

Design Decision: UTC-Based Scheduling
======================================
The Lexicon Crawler uses UTC for all internal scheduling, which **automatically avoids
all DST-related issues**:

1. UTC does not observe DST - it's a constant offset year-round
2. All database timestamps are stored as "timestamp with time zone" in UTC
3. All cron calculations use UTC times
4. croniter library handles UTC correctly without DST complications

DST Issues We Avoid:
--------------------
- **No duplicate runs**: When clocks "fall back" (e.g., 2 AM becomes 1 AM), a local
  time like "2:30 AM" occurs twice. With UTC, there's only one 2:30 AM UTC.

- **No missed runs**: When clocks "spring forward" (e.g., 2 AM becomes 3 AM), local
  times like "2:30 AM" don't exist. With UTC, every hour exists.

- **No ambiguous times**: Local times during DST transitions are ambiguous (which
  2:30 AM?). UTC times are never ambiguous.

Future Timezone Support:
------------------------
If we add support for scheduling in local timezones (non-UTC), this module provides
utilities for detecting and handling DST transitions correctly.
"""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo


def is_dst_transition(dt: datetime, timezone_name: str = "UTC") -> bool:
    """Check if a datetime is during a DST transition.

    Args:
        dt: Datetime to check (timezone-aware or naive UTC)
        timezone_name: IANA timezone name (e.g., "America/New_York", "Europe/London")
            Defaults to "UTC" which never has DST transitions.

    Returns:
        True if the datetime is during a DST transition (spring forward or fall back)
        False otherwise (including for UTC)

    Note:
        UTC never has DST transitions, so this always returns False for UTC.
        This is why the system is DST-safe by default.

    Example:
        >>> from datetime import datetime
        >>> # Spring forward in US Eastern (2 AM doesn't exist)
        >>> dt = datetime(2025, 3, 9, 2, 30)
        >>> is_dst_transition(dt, "America/New_York")
        True
        >>> # Same time in UTC (no DST)
        >>> is_dst_transition(dt, "UTC")
        False
    """
    # Guard: UTC never has DST
    if timezone_name == "UTC":
        return False

    try:
        tz = ZoneInfo(timezone_name)

        # Ensure datetime is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        # Convert to target timezone
        dt_local = dt.astimezone(tz)

        # Check if this time is during a DST transition by looking at surrounding hours
        hour_before = (dt_local - timedelta(hours=1)).dst()
        hour_after = (dt_local + timedelta(hours=1)).dst()

        # DST transition occurs if DST offset changed
        return hour_before != hour_after

    except Exception:
        # If timezone lookup fails, assume no DST
        return False


def get_dst_transition_type(dt: datetime, timezone_name: str = "UTC") -> str | None:
    """Get the type of DST transition at a datetime.

    Args:
        dt: Datetime to check (timezone-aware or naive UTC)
        timezone_name: IANA timezone name

    Returns:
        "spring_forward" if clocks jumped forward (time gap)
        "fall_back" if clocks fell back (time repeat)
        None if not a DST transition or UTC

    Example:
        >>> from datetime import datetime
        >>> # Spring forward: 2 AM -> 3 AM (skip hour)
        >>> dt = datetime(2025, 3, 9, 2, 30)
        >>> get_dst_transition_type(dt, "America/New_York")
        'spring_forward'
        >>> # Fall back: 2 AM -> 1 AM (repeat hour)
        >>> dt = datetime(2025, 11, 2, 1, 30)
        >>> get_dst_transition_type(dt, "America/New_York")
        'fall_back'
    """
    # Guard: UTC never has DST
    if timezone_name == "UTC":
        return None

    if not is_dst_transition(dt, timezone_name):
        return None

    try:
        tz = ZoneInfo(timezone_name)

        # Ensure datetime is timezone-aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)

        # Convert to target timezone
        dt_local = dt.astimezone(tz)

        # Compare DST offset before and after
        hour_before_dst = (dt_local - timedelta(hours=1)).dst()
        hour_after_dst = (dt_local + timedelta(hours=1)).dst()

        if hour_after_dst and hour_after_dst > (hour_before_dst or timedelta(0)):
            return "spring_forward"  # Entering DST (clocks jump forward)
        else:
            return "fall_back"  # Exiting DST (clocks fall back)

    except Exception:
        return None


def safe_next_run_utc(
    cron_expression: str,
    base_time: datetime,
    timezone_name: str = "UTC",
) -> tuple[datetime, str | None]:
    """Calculate next run time with DST awareness and timezone support.

    This function calculates the next run time in the specified timezone,
    handles DST transitions properly, and returns the result in UTC for storage.

    DST Handling:
    - Spring Forward: When clocks jump forward (e.g., 2 AM → 3 AM), if the schedule
      falls in the skipped hour, it runs at the next valid time (3 AM).
    - Fall Back: When clocks fall back (e.g., 2 AM → 1 AM), if the schedule falls
      in the repeated hour, it uses the first occurrence.

    Args:
        cron_expression: Valid cron expression
        base_time: Base time to calculate from (UTC)
        timezone_name: IANA timezone name for schedule calculations
            (e.g., "UTC", "America/New_York", "Asia/Jakarta")

    Returns:
        Tuple of (next_run_time_utc, dst_warning)
        - next_run_time_utc: Next execution time in UTC
        - dst_warning: Description of DST transition if any, None otherwise

    Example:
        >>> from datetime import datetime, UTC
        >>> # Calculate next 2 AM New York time
        >>> base = datetime(2025, 3, 9, 0, 0, tzinfo=UTC)
        >>> next_run, warning = safe_next_run_utc("0 2 * * *", base, "America/New_York")
        >>> # During spring forward, 2 AM doesn't exist, so returns 3 AM with warning
    """
    from crawler.utils.cron import calculate_next_run

    # Calculate next run in user's timezone, converted to UTC
    # The calculate_next_run function now handles timezone conversion
    next_run_utc = calculate_next_run(cron_expression, base_time, timezone_name)

    # Check if this run time falls during a DST transition
    transition_type = get_dst_transition_type(next_run_utc, timezone_name)

    warning = None
    if transition_type == "spring_forward":
        # Convert to local time to show what time it would be
        try:
            tz = ZoneInfo(timezone_name)
            local_time = next_run_utc.astimezone(tz)
            warning = (
                f"Next run falls during spring forward in {timezone_name}. "
                f"Scheduled for {local_time.strftime('%I:%M %p %Z')} (skipped hour adjusted)."
            )
        except Exception:
            warning = f"Next run falls during spring forward in {timezone_name}."
    elif transition_type == "fall_back":
        try:
            tz = ZoneInfo(timezone_name)
            local_time = next_run_utc.astimezone(tz)
            warning = (
                f"Next run falls during fall back in {timezone_name}. "
                f"Scheduled for {local_time.strftime('%I:%M %p %Z')} (first occurrence)."
            )
        except Exception:
            warning = f"Next run falls during fall back in {timezone_name}."

    return next_run_utc, warning
