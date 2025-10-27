"""Unit tests for cron utilities."""

from datetime import UTC, datetime

import pytest

from crawler.utils.cron import calculate_next_run, is_valid_cron


class TestCronValidation:
    """Tests for cron validation utility."""

    def test_is_valid_cron_with_valid_expressions(self) -> None:
        """Test is_valid_cron with valid expressions."""
        valid_crons = [
            "0 0 * * *",  # Daily at midnight
            "*/15 * * * *",  # Every 15 minutes
            "0 12 * * 1",  # Every Monday at noon
            "0 0 1,15 * *",  # Bi-weekly (1st and 15th)
            "0 0 * * 1-5",  # Weekdays only
            "30 2 * * *",  # Daily at 2:30 AM
        ]

        for cron in valid_crons:
            assert is_valid_cron(cron), f"Expected {cron} to be valid"

    def test_is_valid_cron_with_invalid_expressions(self) -> None:
        """Test is_valid_cron with invalid expressions."""
        invalid_crons = [
            "99 0 * * *",  # Invalid minute
            "0 24 * * *",  # Invalid hour
            "0 0 32 * *",  # Invalid day
            "0 0 * 13 *",  # Invalid month
            "0 0 * * 8",  # Invalid weekday
            "invalid",  # Not a cron
            "* * *",  # Too few parts
        ]

        for cron in invalid_crons:
            assert not is_valid_cron(cron), f"Expected {cron} to be invalid"


class TestCalculateNextRun:
    """Tests for calculate_next_run utility."""

    def test_calculate_next_run_daily(self) -> None:
        """Test calculating next run for daily schedule."""
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run("0 0 * * *", base_time)

        # Should be next midnight (2025-01-02 00:00:00)
        assert next_run.day == 2
        assert next_run.hour == 0
        assert next_run.minute == 0

    def test_calculate_next_run_hourly(self) -> None:
        """Test calculating next run for hourly schedule."""
        base_time = datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC)
        next_run = calculate_next_run("0 * * * *", base_time)

        # Should be top of next hour (2025-01-01 11:00:00)
        assert next_run.day == 1
        assert next_run.hour == 11
        assert next_run.minute == 0

    def test_calculate_next_run_every_15_minutes(self) -> None:
        """Test calculating next run for every 15 minutes."""
        base_time = datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC)
        next_run = calculate_next_run("*/15 * * * *", base_time)

        # Should be next 15-minute mark (10:15)
        assert next_run.hour == 10
        assert next_run.minute == 15

    def test_calculate_next_run_specific_days(self) -> None:
        """Test calculating next run for 1st and 15th of month."""
        # Start on Jan 10th
        base_time = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run("0 0 1,15 * *", base_time)

        # Should be Jan 15th at midnight
        assert next_run.day == 15
        assert next_run.month == 1
        assert next_run.hour == 0

    def test_calculate_next_run_weekdays_only(self) -> None:
        """Test calculating next run for weekdays only."""
        # Start on Saturday (2025-01-04 is a Saturday)
        base_time = datetime(2025, 1, 4, 12, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run("0 9 * * 1-5", base_time)

        # Should be Monday (2025-01-06) at 9 AM
        assert next_run.day == 6
        assert next_run.weekday() == 0  # Monday
        assert next_run.hour == 9

    def test_calculate_next_run_without_base_time(self) -> None:
        """Test calculate_next_run uses current time when base_time not provided."""
        next_run = calculate_next_run("0 0 * * *")

        # Should return a future datetime
        assert next_run > datetime.now(UTC)

    def test_calculate_next_run_invalid_cron(self) -> None:
        """Test calculate_next_run with invalid cron expression."""
        with pytest.raises(ValueError):
            calculate_next_run("invalid cron")
