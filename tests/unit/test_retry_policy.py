"""Unit tests for retry policy error classification and backoff calculation."""

from unittest.mock import patch

import pytest

from crawler.db.generated.models import BackoffStrategyEnum, ErrorCategoryEnum
from crawler.services.retry_policy import (
    ErrorClassificationRule,
    calculate_backoff,
    calculate_exponential_backoff,
    calculate_fixed_backoff,
    calculate_linear_backoff,
    classify_exception,
    classify_http_status,
    classify_with_custom_rules,
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

    def test_classify_408_as_timeout(self):
        """408 Request Timeout should be classified as TIMEOUT (not CLIENT_ERROR)."""
        assert classify_http_status(408) == ErrorCategoryEnum.TIMEOUT

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


# ============================================================================
# Logging Tests
# ============================================================================


class TestClassificationLogging:
    """Test that classification decisions are properly logged."""

    @patch("crawler.services.retry_policy.logger")
    def test_http_status_classification_logs_decision(self, mock_logger):
        """Test that HTTP status classification logs the decision."""
        classify_http_status(404, log_decision=True)

        # Should have logged the classification
        mock_logger.info.assert_called_once()
        call_kwargs = mock_logger.info.call_args[1]

        assert call_kwargs["classification_type"] == "http_status"
        assert call_kwargs["status_code"] == 404
        assert call_kwargs["error_category"] == "not_found"
        assert call_kwargs["is_retryable"] is False
        assert "reason" in call_kwargs

    @patch("crawler.services.retry_policy.logger")
    def test_http_status_classification_no_logging(self, mock_logger):
        """Test that logging can be disabled for HTTP status classification."""
        classify_http_status(404, log_decision=False)

        # Should not have logged anything
        mock_logger.info.assert_not_called()
        mock_logger.warning.assert_not_called()

    @patch("crawler.services.retry_policy.logger")
    def test_exception_classification_logs_decision(self, mock_logger):
        """Test that exception classification logs the decision."""
        exc = TimeoutError("Connection timed out")
        classify_exception(exc, log_decision=True)

        # Should have logged the classification
        mock_logger.info.assert_called_once()
        call_kwargs = mock_logger.info.call_args[1]

        assert call_kwargs["classification_type"] == "exception"
        assert call_kwargs["exception_type"] == "TimeoutError"
        assert call_kwargs["error_category"] == "timeout"
        assert call_kwargs["is_retryable"] is True
        assert "reason" in call_kwargs

    @patch("crawler.services.retry_policy.logger")
    def test_exception_classification_no_logging(self, mock_logger):
        """Test that logging can be disabled for exception classification."""
        exc = TimeoutError("Connection timed out")
        classify_exception(exc, log_decision=False)

        # Should not have logged anything
        mock_logger.info.assert_not_called()
        mock_logger.warning.assert_not_called()

    @patch("crawler.services.retry_policy.logger")
    def test_unknown_http_status_logs_warning(self, mock_logger):
        """Test that unknown HTTP status codes log a warning."""
        classify_http_status(999, log_decision=True)

        # Should have logged a warning
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args[1]

        assert call_kwargs["error_category"] == "unknown"
        assert call_kwargs["status_code"] == 999

    @patch("crawler.services.retry_policy.logger")
    def test_unknown_exception_logs_warning(self, mock_logger):
        """Test that unknown exceptions log a warning."""
        exc = RuntimeError("Some random error")
        classify_exception(exc, log_decision=True)

        # Should have logged a warning
        mock_logger.warning.assert_called_once()
        call_kwargs = mock_logger.warning.call_args[1]

        assert call_kwargs["error_category"] == "unknown"
        assert call_kwargs["exception_type"] == "RuntimeError"
        assert call_kwargs["error_message"] == "Some random error"

    @patch("crawler.services.retry_policy.logger")
    def test_retryable_errors_log_info(self, mock_logger):
        """Test that retryable errors (5xx, timeouts, network) log at INFO level."""
        # Server error (retryable)
        classify_http_status(503, log_decision=True)
        assert mock_logger.info.called

        mock_logger.reset_mock()

        # Network error (retryable)
        exc = ConnectionError("Connection refused")
        classify_exception(exc, log_decision=True)
        assert mock_logger.info.called

    @patch("crawler.services.retry_policy.logger")
    def test_permanent_errors_log_info(self, mock_logger):
        """Test that permanent errors (4xx, validation) log at INFO level."""
        # Client error (permanent)
        classify_http_status(404, log_decision=True)
        assert mock_logger.info.called

        mock_logger.reset_mock()

        # Validation error (permanent)
        exc = ValueError("Invalid configuration")
        classify_exception(exc, log_decision=True)
        assert mock_logger.info.called

    @patch("crawler.services.retry_policy.logger")
    def test_browser_crash_logs_warning(self, mock_logger):
        """Test that browser crashes log at WARNING level."""

        # Create a custom exception class to simulate BrowserCrashError
        class BrowserCrashError(Exception):
            pass

        exc = BrowserCrashError("Browser process crashed")
        classify_exception(exc, log_decision=True)
        assert mock_logger.warning.called


# ============================================================================
# Custom Classification Rules Tests
# ============================================================================


class TestCustomClassificationRules:
    """Test custom error classification rules."""

    def test_custom_rule_matches_exception(self):
        """Test that custom rule can match on exception message."""

        def is_custom_rate_limit(exc, status_code):
            """Check if error message contains rate limit keywords."""
            if exc and "rate" in str(exc).lower() and "limit" in str(exc).lower():
                return True
            return False

        rule = ErrorClassificationRule(
            name="custom_rate_limit_detection",
            predicate=is_custom_rate_limit,
            category=ErrorCategoryEnum.RATE_LIMIT,
            reason="Custom rate limit detection via error message keywords",
            is_retryable=True,
        )

        exc = Exception("API rate limit exceeded")
        category, is_retryable = classify_with_custom_rules(
            exc=exc, custom_rules=[rule], log_decision=False
        )

        assert category == ErrorCategoryEnum.RATE_LIMIT
        assert is_retryable is True  # Custom rule override

    def test_custom_rule_matches_status_code(self):
        """Test that custom rule can match on HTTP status code."""

        def is_cloudflare_error(exc, status_code):
            """Check for Cloudflare-specific errors."""
            return status_code in (520, 521, 522, 523, 524)

        rule = ErrorClassificationRule(
            name="cloudflare_errors",
            predicate=is_cloudflare_error,
            category=ErrorCategoryEnum.SERVER_ERROR,
            reason="Cloudflare errors are retryable server issues",
            is_retryable=True,
        )

        category, is_retryable = classify_with_custom_rules(
            http_status=520, custom_rules=[rule], log_decision=False
        )

        assert category == ErrorCategoryEnum.SERVER_ERROR
        assert is_retryable is True  # Custom rule override

    def test_custom_rules_evaluated_in_order(self):
        """Test that custom rules are evaluated in order (first match wins)."""

        def always_match(exc, status_code):
            return True

        rule1 = ErrorClassificationRule(
            name="first_rule",
            predicate=always_match,
            category=ErrorCategoryEnum.NETWORK,
            reason="First rule",
        )

        rule2 = ErrorClassificationRule(
            name="second_rule",
            predicate=always_match,
            category=ErrorCategoryEnum.TIMEOUT,
            reason="Second rule",
        )

        # First rule should win
        category, is_retryable = classify_with_custom_rules(
            exc=Exception("Test"), custom_rules=[rule1, rule2], log_decision=False
        )

        assert category == ErrorCategoryEnum.NETWORK
        assert is_retryable is None  # No override specified

    def test_custom_rule_falls_back_to_standard_classification(self):
        """Test that standard classification is used when no custom rules match."""

        def never_match(exc, status_code):
            return False

        rule = ErrorClassificationRule(
            name="never_matches",
            predicate=never_match,
            category=ErrorCategoryEnum.NETWORK,
            reason="Never matches",
        )

        # Should fall back to standard classification (404 → NOT_FOUND)
        category, is_retryable = classify_with_custom_rules(
            http_status=404, custom_rules=[rule], log_decision=False
        )

        assert category == ErrorCategoryEnum.NOT_FOUND
        assert is_retryable is None  # No custom rule matched, so no override

    def test_custom_rule_with_both_exception_and_status(self):
        """Test custom rule that checks both exception and status code."""

        def is_auth_timeout(exc, status_code):
            """Match if both timeout and 401."""
            return status_code == 401 and exc and "timeout" in str(exc).lower()

        rule = ErrorClassificationRule(
            name="auth_timeout",
            predicate=is_auth_timeout,
            category=ErrorCategoryEnum.TIMEOUT,
            reason="Auth timeout is retryable",
            is_retryable=True,
        )

        exc = Exception("Authentication timeout")
        category, is_retryable = classify_with_custom_rules(
            exc=exc, http_status=401, custom_rules=[rule], log_decision=False
        )

        # Should match custom rule (TIMEOUT) not standard classification (AUTH_ERROR)
        assert category == ErrorCategoryEnum.TIMEOUT
        assert is_retryable is True  # Custom rule override

    @patch("crawler.services.retry_policy.logger")
    def test_custom_rule_logs_when_matched(self, mock_logger):
        """Test that custom rule match is logged."""

        def always_match(exc, status_code):
            return True

        rule = ErrorClassificationRule(
            name="test_rule",
            predicate=always_match,
            category=ErrorCategoryEnum.NETWORK,
            reason="Test reason",
            is_retryable=True,
        )

        classify_with_custom_rules(exc=Exception("Test"), custom_rules=[rule], log_decision=True)

        # Should have logged the custom rule match
        mock_logger.info.assert_called_once()
        call_kwargs = mock_logger.info.call_args[1]

        assert call_kwargs["classification_type"] == "custom_rule"
        assert call_kwargs["rule_name"] == "test_rule"
        assert call_kwargs["error_category"] == "network"
        assert call_kwargs["is_retryable"] is True
        assert call_kwargs["reason"] == "Test reason"

    @patch("crawler.services.retry_policy.logger")
    def test_custom_rule_error_is_logged_and_skipped(self, mock_logger):
        """Test that errors in custom rules are logged and rule is skipped."""

        def broken_predicate(exc, status_code):
            raise ValueError("Predicate crashed")

        rule = ErrorClassificationRule(
            name="broken_rule",
            predicate=broken_predicate,
            category=ErrorCategoryEnum.NETWORK,
            reason="Should not be used",
        )

        # Should skip broken rule and use standard classification
        category, is_retryable = classify_with_custom_rules(
            http_status=404, custom_rules=[rule], log_decision=False
        )

        # Should fall back to standard classification
        assert category == ErrorCategoryEnum.NOT_FOUND
        assert is_retryable is None  # No custom rule matched

        # Should have logged the error
        mock_logger.error.assert_called_once()
        call_kwargs = mock_logger.error.call_args[1]
        assert call_kwargs["rule_name"] == "broken_rule"

    def test_no_custom_rules_uses_standard_classification(self):
        """Test that standard classification is used when no custom rules provided."""
        # Should use standard classification (503 → SERVER_ERROR)
        category, is_retryable = classify_with_custom_rules(http_status=503, log_decision=False)
        assert category == ErrorCategoryEnum.SERVER_ERROR
        assert is_retryable is None  # No custom rules, so no override

    def test_empty_custom_rules_list_uses_standard_classification(self):
        """Test that standard classification is used when custom rules list is empty."""
        category, is_retryable = classify_with_custom_rules(
            http_status=503, custom_rules=[], log_decision=False
        )
        assert category == ErrorCategoryEnum.SERVER_ERROR
        assert is_retryable is None  # No custom rules, so no override

    def test_classify_with_no_error_returns_unknown(self):
        """Test that UNKNOWN is returned when no error or status provided."""
        category, is_retryable = classify_with_custom_rules(log_decision=False)
        assert category == ErrorCategoryEnum.UNKNOWN
        assert is_retryable is None  # No custom rules, so no override

    def test_custom_rule_with_domain_specific_logic(self):
        """Test realistic domain-specific custom rule."""

        def is_shopify_rate_limit(exc, status_code):
            """Detect Shopify-specific rate limiting."""
            # Shopify returns 429 with specific header patterns
            if status_code == 429:
                return True
            # Also check for Shopify error message patterns
            if exc and "shopify" in str(exc).lower() and "throttled" in str(exc).lower():
                return True
            return False

        rule = ErrorClassificationRule(
            name="shopify_rate_limit",
            predicate=is_shopify_rate_limit,
            category=ErrorCategoryEnum.RATE_LIMIT,
            reason="Shopify API rate limiting detected",
            is_retryable=True,
        )

        # Test with status code
        category, is_retryable = classify_with_custom_rules(
            http_status=429, custom_rules=[rule], log_decision=False
        )
        assert category == ErrorCategoryEnum.RATE_LIMIT
        assert is_retryable is True  # Custom rule override

        # Test with exception message
        exc = Exception("Shopify API throttled - too many requests")
        category, is_retryable = classify_with_custom_rules(
            exc=exc, custom_rules=[rule], log_decision=False
        )
        assert category == ErrorCategoryEnum.RATE_LIMIT
        assert is_retryable is True  # Custom rule override

    def test_custom_rule_with_no_retryable_override(self):
        """Test that is_retryable can be None (uses category default)."""

        def always_match(exc, status_code):
            return True

        rule = ErrorClassificationRule(
            name="no_override",
            predicate=always_match,
            category=ErrorCategoryEnum.NETWORK,
            reason="Test",
            is_retryable=None,  # No override - use category default
        )

        category, is_retryable = classify_with_custom_rules(
            exc=Exception("Test"), custom_rules=[rule], log_decision=False
        )

        assert category == ErrorCategoryEnum.NETWORK
        assert is_retryable is None  # No override specified

    def test_custom_rule_validation_empty_name(self):
        """Test that empty name raises ValueError."""

        def always_match(exc, status_code):
            return True

        with pytest.raises(ValueError, match="Rule name cannot be empty"):
            ErrorClassificationRule(
                name="",
                predicate=always_match,
                category=ErrorCategoryEnum.NETWORK,
                reason="Test",
            )

    def test_custom_rule_validation_none_predicate(self):
        """Test that None predicate raises ValueError."""
        with pytest.raises(ValueError, match="Rule predicate cannot be None"):
            ErrorClassificationRule(
                name="test",
                predicate=None,  # type: ignore
                category=ErrorCategoryEnum.NETWORK,
                reason="Test",
            )

    def test_custom_rule_validation_non_callable_predicate(self):
        """Test that non-callable predicate raises ValueError."""
        with pytest.raises(ValueError, match="Rule predicate must be callable"):
            ErrorClassificationRule(
                name="test",
                predicate="not a function",  # type: ignore
                category=ErrorCategoryEnum.NETWORK,
                reason="Test",
            )

    def test_custom_rule_validation_empty_reason(self):
        """Test that empty reason raises ValueError."""

        def always_match(exc, status_code):
            return True

        with pytest.raises(ValueError, match="Rule reason cannot be empty"):
            ErrorClassificationRule(
                name="test",
                predicate=always_match,
                category=ErrorCategoryEnum.NETWORK,
                reason="",
            )

    def test_browser_crash_and_httpx_errors_fallback_to_builtin_classifiers(self):
        """Test browser/httpx errors use built-in classification when custom rules don't match."""

        # Create custom rule that won't match these errors
        def matches_nothing(exc, status_code):
            return False

        rule = ErrorClassificationRule(
            name="never_matches",
            predicate=matches_nothing,
            category=ErrorCategoryEnum.RATE_LIMIT,
            reason="This rule never matches",
        )

        # Test browser crash error falls back to BROWSER_CRASH
        class BrowserCrashError(Exception):
            """Mock browser crash exception."""

        browser_exc = BrowserCrashError("Browser process crashed")
        category, is_retryable = classify_with_custom_rules(
            exc=browser_exc, custom_rules=[rule], log_decision=False
        )
        assert category == ErrorCategoryEnum.BROWSER_CRASH
        assert is_retryable is None  # No custom override, using standard classification

        # Test httpx network error falls back to NETWORK
        class ConnectError(Exception):
            """Mock httpx ConnectError."""

        # Create mock exception with httpx module
        httpx_exc = ConnectError("Connection failed")
        httpx_exc.__class__.__module__ = "httpx"  # Make it look like it's from httpx

        category, is_retryable = classify_with_custom_rules(
            exc=httpx_exc, custom_rules=[rule], log_decision=False
        )
        assert category == ErrorCategoryEnum.NETWORK
        assert is_retryable is None  # No custom override, using standard classification

        # Test Playwright timeout error falls back to TIMEOUT
        class PlaywrightTimeoutError(Exception):
            """Mock Playwright timeout exception."""

        timeout_exc = PlaywrightTimeoutError("Page load timeout")
        category, is_retryable = classify_with_custom_rules(
            exc=timeout_exc, custom_rules=[rule], log_decision=False
        )
        assert category == ErrorCategoryEnum.TIMEOUT
        assert is_retryable is None  # No custom override, using standard classification
