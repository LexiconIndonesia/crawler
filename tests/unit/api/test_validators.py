"""Unit tests for API validators."""

from datetime import UTC, datetime

import pytest

from crawler.api.validators import (
    calculate_next_run_time,
    validate_and_calculate_next_run,
    validate_cron_expression,
)


class TestValidateCronExpression:
    """Tests for validate_cron_expression function."""

    def test_validate_cron_with_valid_expressions(self) -> None:
        """Test validate_cron_expression with valid cron expressions."""
        valid_crons = [
            "0 0 * * *",  # Daily at midnight
            "*/15 * * * *",  # Every 15 minutes
            "0 12 * * 1",  # Every Monday at noon
            "0 0 1,15 * *",  # Bi-weekly (1st and 15th)
            "0 0 * * 1-5",  # Weekdays only
            "30 2 * * *",  # Daily at 2:30 AM
            "0 0 1 * *",  # First day of month
            "*/30 * * * *",  # Every 30 minutes
            "0 2 * * 1",  # Every Monday at 2 AM
        ]

        for cron in valid_crons:
            is_valid, error = validate_cron_expression(cron)
            assert is_valid, f"Expected {cron} to be valid, got error: {error}"
            assert error is None, f"Expected no error for {cron}, got: {error}"

    def test_validate_cron_with_invalid_format(self) -> None:
        """Test validate_cron_expression with invalid format."""
        invalid_crons = [
            ("invalid", "Invalid cron expression format"),
            ("* * *", "Invalid cron expression format"),  # Too few fields
            ("0 0", "Invalid cron expression format"),  # Too few fields
            ("", "Invalid cron expression format"),  # Empty
            ("a b c d e", "Invalid cron expression format"),  # Invalid characters
        ]

        for cron, expected_error_prefix in invalid_crons:
            is_valid, error = validate_cron_expression(cron)
            assert not is_valid, f"Expected {cron} to be invalid"
            assert error is not None
            assert expected_error_prefix in error, (
                f"Expected error to contain '{expected_error_prefix}'"
            )

    def test_validate_cron_with_invalid_values(self) -> None:
        """Test validate_cron_expression with invalid values."""
        invalid_crons = [
            "99 0 * * *",  # Invalid minute (0-59)
            "0 24 * * *",  # Invalid hour (0-23)
            "0 0 32 * *",  # Invalid day (1-31)
            "0 0 * 13 *",  # Invalid month (1-12)
            "0 0 * * 8",  # Invalid weekday (0-7, where 7=0)
        ]

        for cron in invalid_crons:
            is_valid, error = validate_cron_expression(cron)
            assert not is_valid, f"Expected {cron} to be invalid"
            assert error is not None

    def test_validate_cron_with_special_characters(self) -> None:
        """Test validate_cron_expression with special cron characters."""
        valid_crons_with_special = [
            "*/5 * * * *",  # Step values
            "0-30/5 * * * *",  # Range with step
            "0,30 * * * *",  # List values
            "0 0-12/2 * * *",  # Range with step for hours
            "0 0 1-15 * *",  # Range for days
        ]

        for cron in valid_crons_with_special:
            is_valid, error = validate_cron_expression(cron)
            assert is_valid, f"Expected {cron} to be valid, got error: {error}"


class TestCalculateNextRunTime:
    """Tests for calculate_next_run_time function."""

    def test_calculate_next_run_time_daily(self) -> None:
        """Test calculating next run for daily schedule."""
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("0 0 * * *", base_time)

        # Should be next midnight (2025-01-02 00:00:00)
        assert next_run.day == 2
        assert next_run.month == 1
        assert next_run.year == 2025
        assert next_run.hour == 0
        assert next_run.minute == 0
        assert next_run.tzinfo is not None  # Timezone-aware

    def test_calculate_next_run_time_hourly(self) -> None:
        """Test calculating next run for hourly schedule."""
        base_time = datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("0 * * * *", base_time)

        # Should be top of next hour (2025-01-01 11:00:00)
        assert next_run.day == 1
        assert next_run.hour == 11
        assert next_run.minute == 0

    def test_calculate_next_run_time_every_15_minutes(self) -> None:
        """Test calculating next run for every 15 minutes."""
        base_time = datetime(2025, 1, 1, 10, 5, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("*/15 * * * *", base_time)

        # Should be next 15-minute mark (10:15)
        assert next_run.hour == 10
        assert next_run.minute == 15

    def test_calculate_next_run_time_biweekly(self) -> None:
        """Test calculating next run for 1st and 15th of month."""
        # Start on Jan 10th
        base_time = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("0 0 1,15 * *", base_time)

        # Should be Jan 15th at midnight
        assert next_run.day == 15
        assert next_run.month == 1
        assert next_run.hour == 0

    def test_calculate_next_run_time_weekdays_only(self) -> None:
        """Test calculating next run for weekdays only."""
        # Start on Saturday (2025-01-04 is a Saturday)
        base_time = datetime(2025, 1, 4, 12, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("0 9 * * 1-5", base_time)

        # Should be Monday (2025-01-06) at 9 AM
        assert next_run.day == 6
        assert next_run.weekday() == 0  # Monday
        assert next_run.hour == 9

    def test_calculate_next_run_time_without_base_time(self) -> None:
        """Test calculate_next_run_time uses current time when base_time not provided."""
        next_run = calculate_next_run_time("0 0 * * *")

        # Should return a future datetime
        now = datetime.now(UTC)
        assert next_run > now
        assert next_run.tzinfo is not None

    def test_calculate_next_run_time_invalid_cron(self) -> None:
        """Test calculate_next_run_time with invalid cron expression."""
        with pytest.raises(ValueError, match="Invalid cron expression"):
            calculate_next_run_time("invalid cron")

    def test_calculate_next_run_time_timezone_aware(self) -> None:
        """Test that calculate_next_run_time returns timezone-aware datetime."""
        next_run = calculate_next_run_time("0 0 * * *")

        assert next_run.tzinfo is not None
        assert next_run.tzinfo == UTC

    def test_calculate_next_run_time_preserves_timezone(self) -> None:
        """Test that calculate_next_run_time preserves UTC timezone from base_time."""
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("0 12 * * *", base_time)

        assert next_run.tzinfo == UTC


class TestValidateAndCalculateNextRun:
    """Tests for validate_and_calculate_next_run combined function."""

    def test_validate_and_calculate_with_valid_cron(self) -> None:
        """Test validate_and_calculate_next_run with valid cron expression."""
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        is_valid, result = validate_and_calculate_next_run("0 0 * * *", base_time)

        assert is_valid
        assert isinstance(result, datetime)
        assert result > base_time

    def test_validate_and_calculate_with_invalid_cron_format(self) -> None:
        """Test validate_and_calculate_next_run with invalid format."""
        is_valid, result = validate_and_calculate_next_run("invalid")

        assert not is_valid
        assert isinstance(result, str)
        assert "Invalid cron expression format" in result

    def test_validate_and_calculate_with_invalid_cron_values(self) -> None:
        """Test validate_and_calculate_next_run with invalid values."""
        is_valid, result = validate_and_calculate_next_run("99 0 * * *")

        assert not is_valid
        assert isinstance(result, str)

    def test_validate_and_calculate_returns_correct_next_run(self) -> None:
        """Test validate_and_calculate_next_run returns correct next run time."""
        base_time = datetime(2025, 1, 10, 12, 0, 0, tzinfo=UTC)
        is_valid, result = validate_and_calculate_next_run("0 0 1,15 * *", base_time)

        assert is_valid
        assert isinstance(result, datetime)
        assert result.day == 15  # Next occurrence is Jan 15th
        assert result.hour == 0

    def test_validate_and_calculate_without_base_time(self) -> None:
        """Test validate_and_calculate_next_run without base_time."""
        is_valid, result = validate_and_calculate_next_run("0 0 * * *")

        assert is_valid
        assert isinstance(result, datetime)
        assert result > datetime.now(UTC)

    def test_validate_and_calculate_biweekly_schedule(self) -> None:
        """Test validate_and_calculate_next_run with bi-weekly schedule (default)."""
        is_valid, result = validate_and_calculate_next_run("0 0 1,15 * *")

        assert is_valid
        assert isinstance(result, datetime)
        # Result should be either 1st or 15th of current or next month
        assert result.day in [1, 15]


class TestExtendedCronSyntax:
    """Tests for extended cron syntax support (@daily, @weekly, etc.)."""

    def test_validate_extended_syntax_daily(self) -> None:
        """Test validation with @daily extended syntax."""
        is_valid, error = validate_cron_expression("@daily")
        assert is_valid
        assert error is None

    def test_validate_extended_syntax_weekly(self) -> None:
        """Test validation with @weekly extended syntax."""
        is_valid, error = validate_cron_expression("@weekly")
        assert is_valid
        assert error is None

    def test_validate_extended_syntax_monthly(self) -> None:
        """Test validation with @monthly extended syntax."""
        is_valid, error = validate_cron_expression("@monthly")
        assert is_valid
        assert error is None

    def test_validate_extended_syntax_yearly(self) -> None:
        """Test validation with @yearly extended syntax."""
        is_valid, error = validate_cron_expression("@yearly")
        assert is_valid
        assert error is None

    def test_validate_extended_syntax_annually(self) -> None:
        """Test validation with @annually extended syntax."""
        is_valid, error = validate_cron_expression("@annually")
        assert is_valid
        assert error is None

    def test_validate_extended_syntax_hourly(self) -> None:
        """Test validation with @hourly extended syntax."""
        is_valid, error = validate_cron_expression("@hourly")
        assert is_valid
        assert error is None

    def test_validate_extended_syntax_midnight(self) -> None:
        """Test validation with @midnight extended syntax."""
        is_valid, error = validate_cron_expression("@midnight")
        assert is_valid
        assert error is None

    def test_validate_invalid_extended_syntax(self) -> None:
        """Test validation with invalid extended syntax."""
        is_valid, error = validate_cron_expression("@invalid")
        assert not is_valid
        assert error is not None

    def test_calculate_next_run_with_daily_extended(self) -> None:
        """Test calculating next run with @daily extended syntax."""
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("@daily", base_time)

        # Should be next midnight
        assert next_run.day == 2
        assert next_run.hour == 0
        assert next_run.minute == 0
        assert next_run.tzinfo is not None

    def test_calculate_next_run_with_weekly_extended(self) -> None:
        """Test calculating next run with @weekly extended syntax."""
        # Start on Thursday (2025-01-02 is a Thursday)
        base_time = datetime(2025, 1, 2, 10, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("@weekly", base_time)

        # Should be next Sunday at midnight (2025-01-05)
        assert next_run.weekday() == 6  # Sunday
        assert next_run.hour == 0
        assert next_run.minute == 0

    def test_calculate_next_run_with_hourly_extended(self) -> None:
        """Test calculating next run with @hourly extended syntax."""
        base_time = datetime(2025, 1, 1, 10, 30, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("@hourly", base_time)

        # Should be top of next hour
        assert next_run.hour == 11
        assert next_run.minute == 0

    def test_validate_and_calculate_with_daily_extended(self) -> None:
        """Test validate_and_calculate_next_run with @daily."""
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        is_valid, result = validate_and_calculate_next_run("@daily", base_time)

        assert is_valid
        assert isinstance(result, datetime)
        assert result > base_time
        assert result.hour == 0
        assert result.minute == 0

    def test_validate_and_calculate_with_monthly_extended(self) -> None:
        """Test validate_and_calculate_next_run with @monthly."""
        base_time = datetime(2025, 1, 15, 10, 0, 0, tzinfo=UTC)
        is_valid, result = validate_and_calculate_next_run("@monthly", base_time)

        assert is_valid
        assert isinstance(result, datetime)
        # Should be 1st of next month
        assert result.day == 1
        assert result.month == 2
        assert result.hour == 0


class TestTimezoneHandling:
    """Tests for timezone handling in cron calculations."""

    def test_calculate_next_run_with_naive_datetime(self) -> None:
        """Test that naive datetime is assumed to be UTC."""
        # Naive datetime (no timezone info)
        base_time = datetime(2025, 1, 1, 10, 0, 0)
        next_run = calculate_next_run_time("0 12 * * *", base_time)

        # Should return timezone-aware result in UTC
        assert next_run.tzinfo is not None
        assert next_run.tzinfo == UTC
        assert next_run.hour == 12
        assert next_run.day == 1

    def test_calculate_next_run_preserves_utc(self) -> None:
        """Test that UTC timezone is preserved."""
        base_time = datetime(2025, 1, 1, 10, 0, 0, tzinfo=UTC)
        next_run = calculate_next_run_time("0 12 * * *", base_time)

        assert next_run.tzinfo == UTC

    def test_all_results_are_timezone_aware(self) -> None:
        """Test that all cron calculations return timezone-aware datetimes."""
        test_crons = ["0 0 * * *", "@daily", "@weekly", "*/15 * * * *", "0 0 1,15 * *"]

        for cron in test_crons:
            next_run = calculate_next_run_time(cron)
            assert next_run.tzinfo is not None, f"Expected {cron} to return timezone-aware datetime"
            assert next_run.tzinfo == UTC, f"Expected {cron} to return UTC datetime"

    def test_validate_and_calculate_with_naive_datetime(self) -> None:
        """Test validate_and_calculate_next_run handles naive datetime."""
        base_time = datetime(2025, 1, 1, 10, 0, 0)  # Naive
        is_valid, result = validate_and_calculate_next_run("0 0 * * *", base_time)

        assert is_valid
        assert isinstance(result, datetime)
        assert result.tzinfo is not None
        assert result.tzinfo == UTC
