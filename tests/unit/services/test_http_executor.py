"""Unit tests for HTTP executor error classification."""

import pytest

from crawler.services.step_executors.http_executor import classify_http_error


class TestClassifyHTTPError:
    """Tests for classify_http_error function."""

    @pytest.mark.parametrize(
        "status_code,expected_type",
        [
            # 429 is retryable (rate limiting)
            (429, "retryable"),
            # 5xx errors are retryable (server errors)
            (500, "retryable"),
            (501, "retryable"),
            (502, "retryable"),
            (503, "retryable"),
            (504, "retryable"),
            (599, "retryable"),
            # 4xx errors (except 429) are permanent (client errors)
            (400, "permanent"),
            (401, "permanent"),
            (403, "permanent"),
            (404, "permanent"),
            (405, "permanent"),
            (408, "permanent"),
            (410, "permanent"),
            (422, "permanent"),
            (499, "permanent"),
            # 1xx, 3xx, and unknown codes are "unknown"
            (100, "unknown"),
            (101, "unknown"),
            (199, "unknown"),
            (300, "unknown"),
            (301, "unknown"),
            (302, "unknown"),
            (304, "unknown"),
            (399, "unknown"),
            (600, "unknown"),
            (999, "unknown"),
        ],
    )
    def test_classify_http_error(self, status_code: int, expected_type: str) -> None:
        """Test HTTP error classification for various status codes."""
        result = classify_http_error(status_code)
        assert result == expected_type, (
            f"Status code {status_code} should be classified as {expected_type}, but got {result}"
        )

    def test_retryable_errors(self) -> None:
        """Test that all retryable errors are correctly identified."""
        retryable_codes = [429, 500, 502, 503, 504]
        for code in retryable_codes:
            assert classify_http_error(code) == "retryable"

    def test_permanent_errors(self) -> None:
        """Test that all permanent errors (4xx except 429) are correctly identified."""
        permanent_codes = [400, 401, 403, 404, 405, 410, 422]
        for code in permanent_codes:
            assert classify_http_error(code) == "permanent"

    def test_unknown_errors(self) -> None:
        """Test that 1xx, 3xx, and out-of-range codes are classified as unknown."""
        unknown_codes = [100, 101, 300, 301, 302, 304, 600, 999]
        for code in unknown_codes:
            assert classify_http_error(code) == "unknown"

    def test_edge_cases(self) -> None:
        """Test edge cases at boundaries."""
        # 399 is the last 3xx code - should be unknown
        assert classify_http_error(399) == "unknown"

        # 400 is the first 4xx code - should be permanent
        assert classify_http_error(400) == "permanent"

        # 429 is special case within 4xx - should be retryable
        assert classify_http_error(429) == "retryable"

        # 499 is the last 4xx code - should be permanent
        assert classify_http_error(499) == "permanent"

        # 500 is the first 5xx code - should be retryable
        assert classify_http_error(500) == "retryable"

        # 599 is the last standard 5xx code - should be retryable
        assert classify_http_error(599) == "retryable"

        # 600+ are non-standard - should be unknown
        assert classify_http_error(600) == "unknown"
