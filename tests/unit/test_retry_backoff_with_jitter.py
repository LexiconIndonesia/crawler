"""Unit tests for retry backoff with jitter and Retry-After header support."""

import random
from datetime import UTC, datetime, timedelta

from crawler.db.generated.models import BackoffStrategyEnum
from crawler.services.retry_policy import (
    add_jitter,
    calculate_backoff,
    calculate_exponential_backoff,
    parse_retry_after_header,
)

# ============================================================================
# Jitter Tests
# ============================================================================


class TestJitter:
    """Test random jitter functionality."""

    def test_jitter_adds_randomness(self):
        """Jitter should add randomness to delay."""
        random.seed(42)
        base_delay = 10

        # Run multiple times to ensure we get different values
        results = [add_jitter(base_delay, 0.2) for _ in range(100)]

        # Should have multiple unique values due to randomness
        assert len(set(results)) > 1

    def test_jitter_stays_within_range(self):
        """Jitter should stay within specified percentage range."""
        random.seed(42)
        base_delay = 100
        jitter_percent = 0.2  # 20%

        results = [add_jitter(base_delay, jitter_percent) for _ in range(1000)]

        # All results should be within ±20% of base delay
        min_expected = base_delay - int(base_delay * jitter_percent)
        max_expected = base_delay + int(base_delay * jitter_percent)

        assert all(min_expected <= r <= max_expected for r in results)

    def test_jitter_with_small_delay(self):
        """Jitter should work with small delays."""
        random.seed(42)
        base_delay = 1

        result = add_jitter(base_delay, 0.2)

        # Should be 0 or 1 (±20% of 1 is ±0)
        assert result in (0, 1)

    def test_jitter_never_negative(self):
        """Jitter should never produce negative delays."""
        random.seed(42)

        # Even with large jitter on small delays
        results = [add_jitter(2, 0.5) for _ in range(100)]

        assert all(r >= 0 for r in results)

    def test_jitter_with_zero_delay(self):
        """Jitter on zero delay should return zero."""
        random.seed(42)

        result = add_jitter(0, 0.2)

        assert result == 0

    def test_jitter_with_invalid_percent(self):
        """Invalid jitter percent should default to 0.2."""
        random.seed(42)
        base_delay = 10

        # Test negative jitter percent
        result1 = add_jitter(base_delay, -0.5)
        # Test jitter percent > 1.0
        result2 = add_jitter(base_delay, 1.5)

        # Both should fall back to 0.2 (20%) jitter
        # Results should be within 8-12 range (10 ± 2)
        assert 8 <= result1 <= 12
        assert 8 <= result2 <= 12

    def test_jitter_with_different_percentages(self):
        """Test jitter with various percentage values."""
        random.seed(42)
        base_delay = 100

        # Test 10% jitter
        results_10 = [add_jitter(base_delay, 0.1) for _ in range(100)]
        # Test 50% jitter
        results_50 = [add_jitter(base_delay, 0.5) for _ in range(100)]

        # 50% jitter should have wider range than 10%
        range_10 = max(results_10) - min(results_10)
        range_50 = max(results_50) - min(results_50)

        assert range_50 > range_10


# ============================================================================
# Retry-After Header Parsing Tests
# ============================================================================


class TestRetryAfterParsing:
    """Test Retry-After header parsing."""

    def test_parse_retry_after_with_seconds(self):
        """Parse Retry-After with delay-seconds format."""
        assert parse_retry_after_header("120") == 120
        assert parse_retry_after_header("60") == 60
        assert parse_retry_after_header("0") == 0

    def test_parse_retry_after_with_http_date(self):
        """Parse Retry-After with HTTP-date format."""
        # Create a date 2 minutes in the future
        future_time = datetime.now(UTC) + timedelta(minutes=2)
        http_date = future_time.strftime("%a, %d %b %Y %H:%M:%S GMT")

        delay = parse_retry_after_header(http_date)

        # Should be around 120 seconds (allow ±5s for processing time)
        assert delay is not None
        assert 115 <= delay <= 125

    def test_parse_retry_after_with_past_date(self):
        """Retry-After with past date should return 0."""
        # Create a date in the past
        past_time = datetime.now(UTC) - timedelta(hours=1)
        http_date = past_time.strftime("%a, %d %b %Y %H:%M:%S GMT")

        delay = parse_retry_after_header(http_date)

        assert delay == 0

    def test_parse_retry_after_with_none(self):
        """None header should return None."""
        assert parse_retry_after_header(None) is None

    def test_parse_retry_after_with_empty_string(self):
        """Empty string should return None."""
        assert parse_retry_after_header("") is None

    def test_parse_retry_after_with_invalid_format(self):
        """Invalid format should return None."""
        assert parse_retry_after_header("invalid") is None
        assert parse_retry_after_header("not a number") is None
        assert parse_retry_after_header("12.5") is None  # Must be integer

    def test_parse_retry_after_with_malformed_date(self):
        """Malformed HTTP date should return None."""
        assert parse_retry_after_header("Mon, 32 Dec 2025 25:00:00 GMT") is None


# ============================================================================
# Updated Exponential Backoff Formula Tests
# ============================================================================


class TestUpdatedExponentialBackoff:
    """Test updated exponential backoff formula: base^(attempt-1)."""

    def test_exponential_backoff_first_retry(self):
        """First retry (attempt=1) should return initial_delay * base^0 = initial_delay."""
        assert calculate_exponential_backoff(1, 1, 300, 2.0) == 1
        assert calculate_exponential_backoff(1, 5, 300, 2.0) == 5

    def test_exponential_backoff_second_retry(self):
        """Second retry (attempt=2) should return initial_delay * base^1."""
        assert calculate_exponential_backoff(2, 1, 300, 2.0) == 2
        assert calculate_exponential_backoff(2, 5, 300, 2.0) == 10

    def test_exponential_backoff_third_retry(self):
        """Third retry (attempt=3) should return initial_delay * base^2."""
        assert calculate_exponential_backoff(3, 1, 300, 2.0) == 4
        assert calculate_exponential_backoff(3, 5, 300, 2.0) == 20

    def test_exponential_backoff_sequence(self):
        """Test complete exponential sequence."""
        # Formula: initial * base^(attempt-1)
        # With initial=1, base=2: [1, 2, 4, 8, 16, 32, 64, 128, 256, 300]
        attempts = [calculate_exponential_backoff(i, 1, 300, 2.0) for i in range(1, 11)]
        expected = [1, 2, 4, 8, 16, 32, 64, 128, 256, 300]

        assert attempts == expected


# ============================================================================
# Integrated Backoff with Jitter and Retry-After Tests
# ============================================================================


class TestIntegratedBackoff:
    """Test calculate_backoff with all features."""

    def test_backoff_respects_retry_after_header(self):
        """Retry-After header should override calculated delay."""
        delay = calculate_backoff(
            BackoffStrategyEnum.EXPONENTIAL,
            attempt=3,
            initial_delay=1,
            max_delay=300,
            multiplier=2.0,
            retry_after="60",
        )

        # Should use Retry-After value (60s) instead of calculated (4s)
        assert delay == 60

    def test_backoff_with_jitter_varies(self):
        """Backoff with jitter should produce varying results."""
        random.seed(42)

        results = [
            calculate_backoff(
                BackoffStrategyEnum.EXPONENTIAL,
                attempt=3,
                initial_delay=10,
                max_delay=300,
                multiplier=2.0,
                apply_jitter=True,
                jitter_percent=0.2,
            )
            for _ in range(50)
        ]

        # Should have multiple unique values
        assert len(set(results)) > 1

        # All should be around 40 (10 * 2^2) ± 20%
        assert all(32 <= r <= 48 for r in results)

    def test_backoff_without_jitter_is_deterministic(self):
        """Backoff without jitter should be deterministic."""
        results = [
            calculate_backoff(
                BackoffStrategyEnum.EXPONENTIAL,
                attempt=2,
                initial_delay=5,
                max_delay=300,
                multiplier=2.0,
                apply_jitter=False,
            )
            for _ in range(10)
        ]

        # All should be the same
        assert len(set(results)) == 1
        assert results[0] == 10  # 5 * 2^1

    def test_backoff_caps_at_max_delay(self):
        """Backoff should never exceed max_delay."""
        delay = calculate_backoff(
            BackoffStrategyEnum.EXPONENTIAL,
            attempt=20,  # Very large attempt
            initial_delay=1,
            max_delay=100,
            multiplier=2.0,
        )

        assert delay <= 100

    def test_backoff_caps_at_absolute_maximum_300s(self):
        """Backoff should never exceed 300s absolute maximum."""
        delay = calculate_backoff(
            BackoffStrategyEnum.EXPONENTIAL,
            attempt=20,
            initial_delay=1,
            max_delay=1000,  # Try to set higher than 300
            multiplier=2.0,
        )

        assert delay <= 300

    def test_backoff_retry_after_respects_max_delay(self):
        """Retry-After should still be capped at max_delay."""
        delay = calculate_backoff(
            BackoffStrategyEnum.EXPONENTIAL,
            attempt=1,
            initial_delay=1,
            max_delay=50,  # Low max delay
            multiplier=2.0,
            retry_after="120",  # Server says wait 120s
        )

        # Should cap at max_delay
        assert delay == 50


# ============================================================================
# Real-World Integration Scenarios
# ============================================================================


class TestRealWorldScenarios:
    """Test realistic retry scenarios with all features."""

    def test_rate_limit_with_retry_after(self):
        """Rate limit (HTTP 429) with Retry-After header."""
        random.seed(42)

        # Server says "retry after 60 seconds"
        delay = calculate_backoff(
            BackoffStrategyEnum.EXPONENTIAL,
            attempt=1,
            initial_delay=2,
            max_delay=600,
            multiplier=2.0,
            apply_jitter=True,
            jitter_percent=0.1,  # Small jitter for rate limits
            retry_after="60",
        )

        # Should use Retry-After but may have small jitter
        # Wait, Retry-After takes precedence before jitter
        assert delay == 60

    def test_network_error_with_jitter(self):
        """Network error retry with jitter to avoid thundering herd."""
        # Note: Don't set seed here so we get true randomness across iterations

        # Fourth retry of network error (larger delay for visible jitter)
        results = [
            calculate_backoff(
                BackoffStrategyEnum.EXPONENTIAL,
                attempt=4,
                initial_delay=2,
                max_delay=300,
                multiplier=2.0,
                apply_jitter=True,
                jitter_percent=0.2,
            )
            for _ in range(100)
        ]

        # Base delay is 16s (2 * 2^3), with ±20% jitter = ±3s
        # Should be in range 13-19s
        assert all(13 <= r <= 19 for r in results)
        # Should have variation
        assert len(set(results)) > 1

    def test_timeout_linear_backoff_with_jitter(self):
        """Timeout retry with linear backoff and jitter."""
        random.seed(42)

        # Second retry of timeout
        results = [
            calculate_backoff(
                BackoffStrategyEnum.LINEAR,
                attempt=2,
                initial_delay=5,
                max_delay=60,
                multiplier=1.5,
                apply_jitter=True,
                jitter_percent=0.15,
            )
            for _ in range(50)
        ]

        # Base delay is 5 + (1.5 * 2) = 8s, with ±15% jitter
        # Should be mostly in range 6-9s
        assert all(6 <= r <= 9 for r in results)

    def test_progressive_backoff_with_cap(self):
        """Test progressive backoff eventually hits cap."""
        random.seed(42)

        delays = [
            calculate_backoff(
                BackoffStrategyEnum.EXPONENTIAL,
                attempt=i,
                initial_delay=1,
                max_delay=300,
                multiplier=2.0,
                apply_jitter=True,
                jitter_percent=0.1,
            )
            for i in range(1, 15)
        ]

        # First few should grow exponentially
        assert delays[0] < delays[1] < delays[2]

        # Later ones should be capped at 300
        assert delays[-1] <= 300
        assert delays[-2] <= 300
