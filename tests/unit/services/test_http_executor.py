"""Unit tests for HTTP status code classification.

NOTE: These tests use the centralized classify_http_status() from retry_policy.py.
The HTTP executor no longer has its own classification logic - it defers to the retry system.
"""

import pytest

from crawler.db.generated.models import ErrorCategoryEnum
from crawler.services.retry_policy import classify_http_status


class TestClassifyHTTPStatus:
    """Tests for centralized HTTP status code classification."""

    @pytest.mark.parametrize(
        "status_code,expected_category",
        [
            # 404 is NOT_FOUND (special permanent error)
            (404, ErrorCategoryEnum.NOT_FOUND),
            # 401/403 are AUTH_ERROR (special permanent error)
            (401, ErrorCategoryEnum.AUTH_ERROR),
            (403, ErrorCategoryEnum.AUTH_ERROR),
            # 408 is TIMEOUT (retryable)
            (408, ErrorCategoryEnum.TIMEOUT),
            # 429 is RATE_LIMIT (retryable)
            (429, ErrorCategoryEnum.RATE_LIMIT),
            # Other 4xx are CLIENT_ERROR (permanent)
            (400, ErrorCategoryEnum.CLIENT_ERROR),
            (405, ErrorCategoryEnum.CLIENT_ERROR),
            (410, ErrorCategoryEnum.CLIENT_ERROR),
            (422, ErrorCategoryEnum.CLIENT_ERROR),
            (499, ErrorCategoryEnum.CLIENT_ERROR),
            # 5xx errors are SERVER_ERROR (retryable)
            (500, ErrorCategoryEnum.SERVER_ERROR),
            (501, ErrorCategoryEnum.SERVER_ERROR),
            (502, ErrorCategoryEnum.SERVER_ERROR),
            (503, ErrorCategoryEnum.SERVER_ERROR),
            (504, ErrorCategoryEnum.SERVER_ERROR),
            (599, ErrorCategoryEnum.SERVER_ERROR),
            # 1xx, 3xx, and unknown codes are UNKNOWN
            (100, ErrorCategoryEnum.UNKNOWN),
            (101, ErrorCategoryEnum.UNKNOWN),
            (199, ErrorCategoryEnum.UNKNOWN),
            (300, ErrorCategoryEnum.UNKNOWN),
            (301, ErrorCategoryEnum.UNKNOWN),
            (302, ErrorCategoryEnum.UNKNOWN),
            (304, ErrorCategoryEnum.UNKNOWN),
            (399, ErrorCategoryEnum.UNKNOWN),
            (600, ErrorCategoryEnum.UNKNOWN),
            (999, ErrorCategoryEnum.UNKNOWN),
        ],
    )
    def test_classify_http_status(
        self, status_code: int, expected_category: ErrorCategoryEnum
    ) -> None:
        """Test HTTP status classification using centralized retry_policy function."""
        result = classify_http_status(status_code, log_decision=False)
        assert result == expected_category, (
            f"Status code {status_code} should be classified as {expected_category.value}, "
            f"but got {result.value}"
        )

    def test_retryable_errors(self) -> None:
        """Test that retryable errors are correctly identified."""
        retryable_categories = {
            ErrorCategoryEnum.RATE_LIMIT,
            ErrorCategoryEnum.SERVER_ERROR,
            ErrorCategoryEnum.TIMEOUT,
        }
        retryable_codes = [408, 429, 500, 502, 503, 504]
        for code in retryable_codes:
            category = classify_http_status(code, log_decision=False)
            assert category in retryable_categories, (
                f"Status code {code} should be retryable, got {category.value}"
            )

    def test_permanent_errors(self) -> None:
        """Test that permanent errors (4xx) are correctly identified."""
        permanent_categories = {
            ErrorCategoryEnum.NOT_FOUND,
            ErrorCategoryEnum.AUTH_ERROR,
            ErrorCategoryEnum.CLIENT_ERROR,
        }
        permanent_codes = [400, 401, 403, 404, 405, 410, 422]
        for code in permanent_codes:
            category = classify_http_status(code, log_decision=False)
            assert category in permanent_categories, (
                f"Status code {code} should be permanent error, got {category.value}"
            )

    def test_unknown_errors(self) -> None:
        """Test that 1xx, 3xx, and out-of-range codes are classified as unknown."""
        unknown_codes = [100, 101, 300, 301, 302, 304, 600, 999]
        for code in unknown_codes:
            category = classify_http_status(code, log_decision=False)
            assert category == ErrorCategoryEnum.UNKNOWN, (
                f"Status code {code} should be UNKNOWN, got {category.value}"
            )

    def test_edge_cases(self) -> None:
        """Test edge cases at boundaries and special codes."""
        # 399 is the last 3xx code - should be unknown
        assert classify_http_status(399, log_decision=False) == ErrorCategoryEnum.UNKNOWN

        # 400 is the first 4xx code - should be client error
        assert classify_http_status(400, log_decision=False) == ErrorCategoryEnum.CLIENT_ERROR

        # 404 is special case - should be NOT_FOUND
        assert classify_http_status(404, log_decision=False) == ErrorCategoryEnum.NOT_FOUND

        # 408 is special case - should be TIMEOUT
        assert classify_http_status(408, log_decision=False) == ErrorCategoryEnum.TIMEOUT

        # 429 is special case within 4xx - should be RATE_LIMIT
        assert classify_http_status(429, log_decision=False) == ErrorCategoryEnum.RATE_LIMIT

        # 499 is the last 4xx code - should be client error
        assert classify_http_status(499, log_decision=False) == ErrorCategoryEnum.CLIENT_ERROR

        # 500 is the first 5xx code - should be server error
        assert classify_http_status(500, log_decision=False) == ErrorCategoryEnum.SERVER_ERROR

        # 599 is the last standard 5xx code - should be server error
        assert classify_http_status(599, log_decision=False) == ErrorCategoryEnum.SERVER_ERROR

        # 600+ are non-standard - should be unknown
        assert classify_http_status(600, log_decision=False) == ErrorCategoryEnum.UNKNOWN
