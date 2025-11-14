"""Unit tests for retry policy error classification and backoff calculation."""

import pytest

from crawler.db.generated.models import BackoffStrategyEnum, ErrorCategoryEnum
from crawler.services.retry_policy import (
    calculate_backoff,
    calculate_exponential_backoff,
    calculate_fixed_backoff,
    calculate_linear_backoff,
    classify_exception,
    classify_http_status,
    get_error_context,
)

# ============================================================================
# HTTP Status Code Classification Tests
# ============================================================================


class TestHTTPStatusClassification:
    """Test HTTP status code to error category mapping."""

    def test_classify_404_as_not_found(self):
        """404 should be classified as NOT_FOUND."""
        assert classify_http_status(404) == ErrorCategoryEnum.NOT_FOUND

    def test_classify_401_as_auth_error(self):
        """401 should be classified as AUTH_ERROR."""
        assert classify_http_status(401) == ErrorCategoryEnum.AUTH_ERROR

    def test_classify_403_as_auth_error(self):
        """403 should be classified as AUTH_ERROR."""
        assert classify_http_status(403) == ErrorCategoryEnum.AUTH_ERROR

    def test_classify_429_as_rate_limit(self):
        """429 should be classified as RATE_LIMIT."""
        assert classify_http_status(429) == ErrorCategoryEnum.RATE_LIMIT

    @pytest.mark.parametrize("status_code", [400, 405, 410, 422, 451])
    def test_classify_other_4xx_as_client_error(self, status_code):
        """Other 4xx codes should be classified as CLIENT_ERROR."""
        assert classify_http_status(status_code) == ErrorCategoryEnum.CLIENT_ERROR

    @pytest.mark.parametrize("status_code", [500, 502, 503, 504])
    def test_classify_5xx_as_server_error(self, status_code):
        """5xx codes should be classified as SERVER_ERROR."""
        assert classify_http_status(status_code) == ErrorCategoryEnum.SERVER_ERROR

    @pytest.mark.parametrize("status_code", [200, 201, 301, 302, 304])
    def test_classify_non_error_codes_as_unknown(self, status_code):
        """Non-error status codes should be classified as UNKNOWN."""
        assert classify_http_status(status_code) == ErrorCategoryEnum.UNKNOWN


# ============================================================================
# Exception Classification Tests
# ============================================================================


class TestExceptionClassification:
    """Test exception to error category mapping."""

    def test_classify_connection_error_as_network(self):
        """ConnectionError should be classified as NETWORK."""
        exc = ConnectionError("Connection refused")
        assert classify_exception(exc) == ErrorCategoryEnum.NETWORK

    def test_classify_timeout_error_as_timeout(self):
        """TimeoutError should be classified as TIMEOUT."""
        exc = TimeoutError("Connection timed out")
        assert classify_exception(exc) == ErrorCategoryEnum.TIMEOUT

    def test_classify_validation_error_as_validation_error(self):
        """ValueError should be classified as VALIDATION_ERROR."""
        exc = ValueError("Invalid configuration")
        assert classify_exception(exc) == ErrorCategoryEnum.VALIDATION_ERROR

    def test_classify_memory_error_as_resource_unavailable(self):
        """MemoryError should be classified as RESOURCE_UNAVAILABLE."""
        exc = MemoryError("Out of memory")
        assert classify_exception(exc) == ErrorCategoryEnum.RESOURCE_UNAVAILABLE

    def test_classify_unknown_exception_as_unknown(self):
        """Unknown exceptions should be classified as UNKNOWN."""
        exc = RuntimeError("Some random error")
        assert classify_exception(exc) == ErrorCategoryEnum.UNKNOWN

    def test_get_error_context_includes_stack_trace(self):
        """get_error_context should include exception details."""
        exc = ValueError("Test error")
        context = get_error_context(exc)

        assert context["exception_type"] == "ValueError"
        assert context["exception_module"] == "builtins"
        assert context["error_message"] == "Test error"
        assert "stack_trace" in context
        # Note: traceback.format_exc() returns "NoneType: None\n" when not in except block
        assert context["stack_trace"] is not None


# ============================================================================
# Backoff Calculation Tests
# ============================================================================


class TestExponentialBackoff:
    """Test exponential backoff calculation with formula: base^(attempt-1)."""

    def test_exponential_backoff_first_attempt(self):
        """First attempt (attempt=1) should return initial_delay * multiplier^0 = initial_delay."""
        assert calculate_exponential_backoff(1, 1, 300, 2.0) == 1

    def test_exponential_backoff_second_attempt(self):
        """Second attempt (attempt=2) should return initial_delay * multiplier^1."""
        assert calculate_exponential_backoff(2, 1, 300, 2.0) == 2

    def test_exponential_backoff_third_attempt(self):
        """Third attempt (attempt=3) should return initial_delay * multiplier^2."""
        assert calculate_exponential_backoff(3, 1, 300, 2.0) == 4

    def test_exponential_backoff_respects_max_delay(self):
        """Exponential backoff should cap at max_delay."""
        # 2^10 = 1024, but max_delay = 300
        assert calculate_exponential_backoff(11, 1, 300, 2.0) == 300

    def test_exponential_backoff_with_higher_multiplier(self):
        """Test with different multiplier."""
        # 1 * 3^3 = 27
        assert calculate_exponential_backoff(4, 1, 300, 3.0) == 27

    def test_exponential_backoff_with_larger_initial_delay(self):
        """Test with larger initial delay."""
        # 5 * 2^2 = 20
        assert calculate_exponential_backoff(3, 5, 300, 2.0) == 20


class TestLinearBackoff:
    """Test linear backoff calculation."""

    def test_linear_backoff_first_attempt(self):
        """First attempt should return initial_delay."""
        # attempt=1: 5 + (1.5 * 0) = 5
        assert calculate_linear_backoff(1, 5, 60, 1.5) == 5

    def test_linear_backoff_second_attempt(self):
        """Second attempt should return initial_delay + multiplier."""
        # attempt=2: 5 + (1.5 * 1) = 6.5 → 6
        assert calculate_linear_backoff(2, 5, 60, 1.5) == 6

    def test_linear_backoff_third_attempt(self):
        """Third attempt should return initial_delay + (multiplier * 2)."""
        # attempt=3: 5 + (1.5 * 2) = 8
        assert calculate_linear_backoff(3, 5, 60, 1.5) == 8

    def test_linear_backoff_respects_max_delay(self):
        """Linear backoff should cap at max_delay."""
        # attempt=51: 5 + (1.5 * 50) = 80, but max_delay = 60
        assert calculate_linear_backoff(51, 5, 60, 1.5) == 60

    def test_linear_backoff_with_integer_multiplier(self):
        """Test linear backoff with integer multiplier."""
        # attempt=4: 10 + (2 * 3) = 16
        assert calculate_linear_backoff(4, 10, 100, 2.0) == 16


class TestFixedBackoff:
    """Test fixed backoff calculation."""

    def test_fixed_backoff_returns_initial_delay(self):
        """Fixed backoff should always return initial_delay."""
        assert calculate_fixed_backoff(10, 60) == 10

    def test_fixed_backoff_respects_max_delay(self):
        """Fixed backoff should cap at max_delay."""
        assert calculate_fixed_backoff(100, 60) == 60

    def test_fixed_backoff_with_equal_values(self):
        """Test when initial_delay equals max_delay."""
        assert calculate_fixed_backoff(30, 30) == 30


class TestBackoffStrategyDispatch:
    """Test the main calculate_backoff function with different strategies."""

    def test_calculate_backoff_exponential(self):
        """Test calculate_backoff with EXPONENTIAL strategy."""
        delay = calculate_backoff(BackoffStrategyEnum.EXPONENTIAL, 3, 1, 300, 2.0)
        assert delay == 4  # 1 * 2^(3-1) = 1 * 2^2 = 4

    def test_calculate_backoff_linear(self):
        """Test calculate_backoff with LINEAR strategy."""
        delay = calculate_backoff(BackoffStrategyEnum.LINEAR, 3, 5, 60, 1.5)
        assert delay == 8  # 5 + (1.5 * (3-1)) = 5 + 3 = 8

    def test_calculate_backoff_fixed(self):
        """Test calculate_backoff with FIXED strategy."""
        delay = calculate_backoff(BackoffStrategyEnum.FIXED, 5, 10, 60, 2.0)
        assert delay == 10  # Always 10 (attempt number doesn't matter)

    def test_calculate_backoff_with_invalid_strategy(self):
        """Test calculate_backoff raises ValueError for unknown strategy."""
        with pytest.raises(ValueError, match="Unknown backoff strategy"):
            calculate_backoff("invalid_strategy", 1, 1, 300, 2.0)  # type: ignore


# ============================================================================
# Edge Cases and Boundary Tests
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_exponential_backoff_with_first_attempt(self):
        """Exponential backoff with attempt=1 should return initial delay."""
        assert calculate_exponential_backoff(1, 10, 300, 2.0) == 10

    def test_exponential_backoff_with_multiplier_one(self):
        """Exponential backoff with multiplier=1.0 should return initial delay."""
        # 10 * 1.0^5 = 10
        assert calculate_exponential_backoff(5, 10, 300, 1.0) == 10

    def test_linear_backoff_with_zero_multiplier(self):
        """Linear backoff with multiplier=0 should return initial delay."""
        assert calculate_linear_backoff(10, 20, 300, 0.0) == 20

    def test_backoff_with_very_small_max_delay(self):
        """All backoff strategies should respect very small max_delay."""
        assert calculate_exponential_backoff(10, 1, 1, 2.0) == 1
        assert calculate_linear_backoff(10, 5, 1, 1.5) == 1
        assert calculate_fixed_backoff(100, 1) == 1

    def test_exponential_backoff_large_attempt_number(self):
        """Exponential backoff with very large attempt should cap at max_delay."""
        # 2^1000 is astronomically large, should cap at 300
        assert calculate_exponential_backoff(1000, 1, 300, 2.0) == 300


# ============================================================================
# Real-World Scenario Tests
# ============================================================================


class TestRealWorldScenarios:
    """Test realistic retry scenarios."""

    def test_rate_limit_retry_schedule(self):
        """Test realistic rate limit retry schedule (exponential with base 2.0)."""
        # Simulate rate limit policy: initial=2s, max=600s, multiplier=2.0
        # Using 1-indexed attempts: 1, 2, 3, 4, 5, 6
        attempts = [calculate_exponential_backoff(i, 2, 600, 2.0) for i in range(1, 7)]

        # Expected: [2, 4, 8, 16, 32, 64] seconds
        assert attempts == [2, 4, 8, 16, 32, 64]

    def test_network_error_retry_schedule(self):
        """Test realistic network error retry schedule (exponential with base 2.0)."""
        # Simulate network error policy: initial=1s, max=300s, multiplier=2.0
        # Using 1-indexed attempts: 1, 2, 3, 4, 5, 6, 7, 8, 9, 10
        attempts = [calculate_exponential_backoff(i, 1, 300, 2.0) for i in range(1, 11)]

        # Expected: [1, 2, 4, 8, 16, 32, 64, 128, 256, 300] (capped at 300)
        assert attempts == [1, 2, 4, 8, 16, 32, 64, 128, 256, 300]

    def test_timeout_retry_schedule(self):
        """Test realistic timeout retry schedule (linear with multiplier 1.5)."""
        # Simulate timeout policy: initial=5s, max=60s, multiplier=1.5
        # Use 1-indexed attempts (1, 2, 3, 4, 5)
        attempts = [calculate_linear_backoff(i, 5, 60, 1.5) for i in range(1, 6)]

        # Expected: [5, 6, 8, 9, 11] seconds (5 + 1.5*(i-1), as integers)
        assert attempts == [5, 6, 8, 9, 11]

    def test_unknown_error_retry_schedule(self):
        """Test conservative unknown error retry (fixed backoff)."""
        # Simulate unknown error policy: fixed 10s delay
        attempts = [calculate_fixed_backoff(10, 10) for _ in range(5)]

        # Expected: always 10 seconds
        assert attempts == [10, 10, 10, 10, 10]
