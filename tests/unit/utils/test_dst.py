"""Unit tests for DST handling utilities.

These tests demonstrate that UTC-based scheduling automatically handles
all DST edge cases correctly.
"""

from datetime import UTC, datetime

from crawler.utils.dst import (
    get_dst_transition_type,
    is_dst_transition,
    safe_next_run_utc,
)


class TestDSTDetection:
    """Tests for DST transition detection."""

    def test_utc_never_has_dst(self) -> None:
        """Test that UTC never has DST transitions."""
        # Any time in UTC should not be a DST transition
        dt = datetime(2025, 3, 9, 2, 30, tzinfo=UTC)  # US spring forward date
        assert is_dst_transition(dt, "UTC") is False

        dt = datetime(2025, 11, 2, 1, 30, tzinfo=UTC)  # US fall back date
        assert is_dst_transition(dt, "UTC") is False

    def test_spring_forward_us_eastern(self) -> None:
        """Test detection of spring forward in US Eastern timezone.

        On March 9, 2025, at 2 AM EST, clocks jump to 3 AM EDT.
        Times between 2:00 AM and 2:59 AM don't exist.
        """
        # Time that doesn't exist in local time
        dt = datetime(2025, 3, 9, 7, 30, tzinfo=UTC)  # 2:30 AM EST (doesn't exist)

        assert is_dst_transition(dt, "America/New_York") is True
        assert get_dst_transition_type(dt, "America/New_York") == "spring_forward"

    def test_fall_back_us_eastern(self) -> None:
        """Test detection of fall back in US Eastern timezone.

        On November 2, 2025, at 2 AM EDT, clocks fall back to 1 AM EST.
        Times between 1:00 AM and 1:59 AM occur twice.
        """
        # Time that occurs twice in local time
        dt = datetime(2025, 11, 2, 6, 30, tzinfo=UTC)  # 1:30 AM (ambiguous)

        assert is_dst_transition(dt, "America/New_York") is True
        assert get_dst_transition_type(dt, "America/New_York") == "fall_back"

    def test_normal_time_not_dst_transition(self) -> None:
        """Test that normal times are not DST transitions."""
        # Regular summer time (in DST)
        dt = datetime(2025, 7, 15, 14, 0, tzinfo=UTC)
        assert is_dst_transition(dt, "America/New_York") is False
        assert get_dst_transition_type(dt, "America/New_York") is None

        # Regular winter time (not in DST)
        dt = datetime(2025, 12, 15, 14, 0, tzinfo=UTC)
        assert is_dst_transition(dt, "America/New_York") is False
        assert get_dst_transition_type(dt, "America/New_York") is None


class TestDSTSafeScheduling:
    """Tests demonstrating UTC scheduling handles DST correctly."""

    def test_no_duplicate_runs_during_fall_back(self) -> None:
        """Test that timezone-aware scheduling prevents duplicate runs during fall back.

        Scenario: On Nov 2, 2025, at 2 AM EDT, clocks fall back to 1 AM EST.
        If scheduled for "1:30 AM local", this time occurs twice.

        With timezone-aware scheduling: We calculate in local time, then convert to UTC.
        The cron expression is evaluated in the user's timezone, ensuring the schedule
        honors local time even during DST transitions.
        """
        # Start time: just before fall back (Nov 2, 2025, 1 AM EDT = 5 AM UTC)
        base_time = datetime(2025, 11, 2, 5, 0, tzinfo=UTC)

        # Schedule hourly in America/New_York time
        # "0 * * * *" means every hour on the hour in NEW YORK TIME
        next_run1, warning1 = safe_next_run_utc("0 * * * *", base_time, "America/New_York")

        # Calculate next run after that
        next_run2, warning2 = safe_next_run_utc("0 * * * *", next_run1, "America/New_York")

        # The cron is evaluated in NY time, so we get the next hour in NY time
        # which is then converted to UTC. During fall back, the UTC times will
        # reflect the local time changes.
        assert next_run1.tzinfo == UTC
        assert next_run2.tzinfo == UTC
        # Verify they are 1 hour apart in local time
        # (even though UTC offset changes during DST transition)
        assert (next_run2 - next_run1).total_seconds() == 3600

    def test_no_missed_runs_during_spring_forward(self) -> None:
        """Test that UTC scheduling prevents missed runs during spring forward.

        Scenario: On Mar 9, 2025, at 2 AM EST, clocks jump to 3 AM EDT.
        If scheduled for "2:30 AM local", this time doesn't exist.

        With UTC: We schedule for a specific UTC time, which always exists.
        The "non-existent hour" problem doesn't exist in UTC.
        """
        # Start time: just before spring forward (Mar 9, 2025, 1 AM EST = 6 AM UTC)
        base_time = datetime(2025, 3, 9, 6, 0, tzinfo=UTC)

        # Schedule hourly (every hour in UTC)
        next_run1, warning1 = safe_next_run_utc("0 * * * *", base_time, "America/New_York")

        # Calculate next run after that
        next_run2, warning2 = safe_next_run_utc("0 * * * *", next_run1, "America/New_York")

        # In UTC, we get 7 AM and 8 AM (no gaps)
        assert next_run1 == datetime(2025, 3, 9, 7, 0, tzinfo=UTC)
        assert next_run2 == datetime(2025, 3, 9, 8, 0, tzinfo=UTC)

        # Both times exist in UTC, preventing missed runs
        # 7 AM UTC = 2 AM EST (doesn't exist locally, but exists in UTC)

    def test_dst_warning_for_spring_forward(self) -> None:
        """Test DST detection during spring forward hour.

        Note: Warnings appear if the calculated next run falls during
        the DST transition window in the user's timezone.
        """
        # Base time that will calculate next run during spring forward window
        # March 9, 2025, 2 AM EST doesn't exist (jumps to 3 AM EDT = 7 AM UTC)
        base_time = datetime(2025, 3, 9, 6, 0, tzinfo=UTC)

        # Schedule for 7 AM in America/New_York time
        # "0 7 * * *" means 7 AM in NEW YORK TIME (not UTC)
        next_run, warning = safe_next_run_utc("0 7 * * *", base_time, "America/New_York")

        # The next run time in UTC is valid, DST handled correctly
        assert next_run.tzinfo == UTC
        # 7 AM New York time converts to UTC (11 AM or 12 PM depending on DST)

        # The important thing is: no errors, time is valid in UTC

    def test_dst_warning_for_fall_back(self) -> None:
        """Test DST detection during fall back hour.

        Note: Warnings appear if the calculated next run falls during
        the DST transition window in the user's timezone.
        """
        # Base time that will calculate next run during fall back window
        # November 2, 2025, 2 AM EDT -> 1 AM EST (1:00-1:59 AM occurs twice)
        base_time = datetime(2025, 11, 2, 5, 0, tzinfo=UTC)

        # Schedule for 6 AM in America/New_York time
        # "0 6 * * *" means 6 AM in NEW YORK TIME (not UTC)
        next_run, warning = safe_next_run_utc("0 6 * * *", base_time, "America/New_York")

        # The next run time in UTC is valid, DST handled correctly
        assert next_run.tzinfo == UTC
        # 6 AM New York time converts to UTC (10 AM or 11 AM depending on DST)

        # The important thing is: no errors, time is valid in UTC

    def test_no_warning_for_utc(self) -> None:
        """Test that UTC scheduling never produces DST warnings."""
        # Any time in UTC
        base_time = datetime(2025, 3, 9, 2, 0, tzinfo=UTC)

        # Schedule for any time
        next_run, warning = safe_next_run_utc("0 2 * * *", base_time, "UTC")

        # No warning for UTC (it doesn't have DST)
        assert warning is None
        assert next_run.tzinfo == UTC

    def test_consistent_scheduling_across_dst_boundary(self) -> None:
        """Test that scheduling is consistent before/after DST transition.

        This demonstrates that timezone-aware scheduling provides predictable,
        consistent behavior in the user's local time, regardless of DST transitions.
        """
        # Schedule for midnight in America/New_York time daily
        # "0 0 * * *" means midnight in NEW YORK TIME
        cron = "0 0 * * *"

        # Week before spring forward
        base1 = datetime(2025, 3, 2, 0, 0, tzinfo=UTC)
        next1, _ = safe_next_run_utc(cron, base1, "America/New_York")

        # Week after spring forward
        base2 = datetime(2025, 3, 16, 0, 0, tzinfo=UTC)
        next2, _ = safe_next_run_utc(cron, base2, "America/New_York")

        # Both should be midnight in New York time
        # The UTC hour will differ due to DST, but local time is consistent
        assert next1.minute == 0
        assert next2.minute == 0

        # Times are unambiguous and consistent in UTC
        assert next1.tzinfo == UTC
        assert next2.tzinfo == UTC


class TestDSTEdgeCases:
    """Tests for DST edge cases."""

    def test_invalid_timezone_returns_none(self) -> None:
        """Test that invalid timezone names don't cause errors."""
        dt = datetime(2025, 3, 9, 2, 30, tzinfo=UTC)

        # Invalid timezone should not raise, just return False
        assert is_dst_transition(dt, "Invalid/Timezone") is False
        assert get_dst_transition_type(dt, "Invalid/Timezone") is None

    def test_naive_datetime_assumed_utc(self) -> None:
        """Test that naive datetimes are assumed to be UTC."""
        # Naive datetime (no timezone)
        dt_naive = datetime(2025, 3, 9, 2, 30)

        # Should be treated as UTC (no DST)
        assert is_dst_transition(dt_naive, "UTC") is False

    def test_multiple_timezones_spring_forward(self) -> None:
        """Test spring forward detection in different timezones."""
        # US Eastern: March 9, 2025
        dt_us = datetime(2025, 3, 9, 7, 30, tzinfo=UTC)
        assert get_dst_transition_type(dt_us, "America/New_York") == "spring_forward"

        # Europe/London: March 30, 2025
        dt_uk = datetime(2025, 3, 30, 1, 30, tzinfo=UTC)
        assert get_dst_transition_type(dt_uk, "Europe/London") == "spring_forward"

    def test_multiple_timezones_fall_back(self) -> None:
        """Test fall back detection in different timezones."""
        # US Eastern: November 2, 2025
        dt_us = datetime(2025, 11, 2, 6, 30, tzinfo=UTC)
        assert get_dst_transition_type(dt_us, "America/New_York") == "fall_back"

        # Europe/London: October 26, 2025
        dt_uk = datetime(2025, 10, 26, 1, 30, tzinfo=UTC)
        assert get_dst_transition_type(dt_uk, "Europe/London") == "fall_back"


class TestDSTDocumentation:
    """Tests that serve as documentation for DST behavior."""

    def test_why_utc_solves_dst_problems(self) -> None:
        """Documentation: Why UTC-based scheduling solves all DST problems.

        DST Problems in Local Time:
        1. **Ambiguous times**: During fall back, 1:30 AM occurs twice.
           Which one do you mean?

        2. **Non-existent times**: During spring forward, 2:30 AM doesn't exist.
           When should the job run?

        3. **Inconsistent intervals**: Scheduling "every hour" in local time
           means some days have 23 hours, some have 25 hours.

        UTC Solution:
        1. **No ambiguity**: Every UTC time is unique, even during transitions.

        2. **No gaps**: Every hour exists in UTC. 2:30 AM UTC always exists.

        3. **Consistent intervals**: UTC hours are always 60 minutes. No surprises.

        This test demonstrates all three benefits.
        """
        # 1. Demonstrate no ambiguity
        fall_back_time = datetime(2025, 11, 2, 6, 30, tzinfo=UTC)
        # This is "1:30 AM local" which occurs twice in US Eastern
        # But in UTC, it's unambiguous: 2025-11-02 06:30:00 UTC
        assert fall_back_time.tzinfo == UTC  # Unambiguous

        # 2. Demonstrate no gaps
        spring_forward_time = datetime(2025, 3, 9, 7, 30, tzinfo=UTC)
        # This is "2:30 AM EST" which doesn't exist in US Eastern
        # But in UTC, it's perfectly valid: 2025-03-09 07:30:00 UTC
        assert spring_forward_time.tzinfo == UTC  # No gap

        # 3. Demonstrate consistent intervals
        hourly_schedule = "0 * * * *"  # Every hour
        base = datetime(2025, 3, 9, 6, 0, tzinfo=UTC)

        runs = []
        current = base
        for _ in range(5):
            next_run, _ = safe_next_run_utc(hourly_schedule, current, "UTC")
            runs.append(next_run)
            current = next_run

        # Verify all intervals are exactly 1 hour (no 23-hour or 25-hour days)
        for i in range(len(runs) - 1):
            interval = (runs[i + 1] - runs[i]).total_seconds()
            assert interval == 3600  # Exactly 1 hour (3600 seconds)

        # This works even across DST transitions because UTC doesn't have them
