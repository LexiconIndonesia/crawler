"""Unit tests for executor retry logic."""

from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from crawler.services.executor_retry import execute_with_retry
from crawler.services.step_executors.base import ExecutionResult


class TestExecuteWithRetry:
    """Tests for execute_with_retry function."""

    async def test_no_retry_config_executes_once(self) -> None:
        """Test that without retry config, function executes exactly once."""
        mock_func = AsyncMock(return_value=ExecutionResult(success=True, content="test"))

        result = await execute_with_retry(
            func=mock_func,
            retry_config=None,
            operation_name="test_op",
            url="https://example.com",
        )

        assert result.success is True
        assert mock_func.call_count == 1

    async def test_max_attempts_one_executes_once(self) -> None:
        """Test that max_attempts=1 executes exactly once without retry."""
        mock_func = AsyncMock(return_value=ExecutionResult(success=True, content="test"))

        result = await execute_with_retry(
            func=mock_func,
            retry_config={"max_attempts": 1},
            operation_name="test_op",
            url="https://example.com",
        )

        assert result.success is True
        assert mock_func.call_count == 1

    async def test_successful_execution_no_retry(self) -> None:
        """Test that successful execution doesn't retry."""
        mock_func = AsyncMock(return_value=ExecutionResult(success=True, content="success"))

        result = await execute_with_retry(
            func=mock_func,
            retry_config={"max_attempts": 3},
            operation_name="test_op",
            url="https://example.com",
        )

        assert result.success is True
        assert mock_func.call_count == 1

    async def test_retryable_error_retries_and_succeeds(self) -> None:
        """Test that retryable errors trigger retry and eventually succeed."""
        # First call fails with 503 (retryable), second call succeeds
        mock_func = AsyncMock(
            side_effect=[
                ExecutionResult(success=False, error="503 error", status_code=503),
                ExecutionResult(success=True, content="success"),
            ]
        )

        with patch("crawler.services.executor_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await execute_with_retry(
                func=mock_func,
                retry_config={
                    "max_attempts": 3,
                    "initial_delay_seconds": 0.1,
                    "backoff_strategy": "fixed",
                },
                operation_name="test_op",
                url="https://example.com",
            )

        assert result.success is True
        assert mock_func.call_count == 2

    async def test_permanent_error_no_retry(self) -> None:
        """Test that permanent errors (404) don't trigger retry."""
        mock_func = AsyncMock(
            return_value=ExecutionResult(success=False, error="404 not found", status_code=404)
        )

        result = await execute_with_retry(
            func=mock_func,
            retry_config={"max_attempts": 3},
            operation_name="test_op",
            url="https://example.com",
        )

        assert result.success is False
        assert result.status_code == 404
        assert mock_func.call_count == 1  # No retries for permanent error

    async def test_all_retries_exhausted_returns_failure(self) -> None:
        """Test that all retries exhausted returns final failure result."""
        mock_func = AsyncMock(
            return_value=ExecutionResult(success=False, error="503 error", status_code=503)
        )

        with patch("crawler.services.executor_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await execute_with_retry(
                func=mock_func,
                retry_config={
                    "max_attempts": 3,
                    "initial_delay_seconds": 0.1,
                    "backoff_strategy": "fixed",
                },
                operation_name="test_op",
                url="https://example.com",
            )

        assert result.success is False
        assert result.status_code == 503
        assert mock_func.call_count == 3  # All attempts used

    async def test_retryable_exception_retries(self) -> None:
        """Test that retryable exceptions (TimeoutError) trigger retry."""
        mock_func = AsyncMock(
            side_effect=[
                TimeoutError("Connection timeout"),
                ExecutionResult(success=True, content="success"),
            ]
        )

        with patch("crawler.services.executor_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await execute_with_retry(
                func=mock_func,
                retry_config={
                    "max_attempts": 3,
                    "initial_delay_seconds": 0.1,
                    "backoff_strategy": "fixed",
                },
                operation_name="test_op",
                url="https://example.com",
            )

        assert result.success is True
        assert mock_func.call_count == 2

    async def test_permanent_exception_no_retry(self) -> None:
        """Test that permanent exceptions (ValueError) don't trigger retry."""
        mock_func = AsyncMock(side_effect=ValueError("Invalid input"))

        with pytest.raises(ValueError, match="Invalid input"):
            await execute_with_retry(
                func=mock_func,
                retry_config={"max_attempts": 3},
                operation_name="test_op",
                url="https://example.com",
            )

        assert mock_func.call_count == 1  # No retries for permanent error

    async def test_exception_retries_exhausted_raises(self) -> None:
        """Test that exception retries exhausted raises the exception."""
        mock_func = AsyncMock(side_effect=TimeoutError("Connection timeout"))

        with patch("crawler.services.executor_retry.asyncio.sleep", new_callable=AsyncMock):
            with pytest.raises(TimeoutError, match="Connection timeout"):
                await execute_with_retry(
                    func=mock_func,
                    retry_config={
                        "max_attempts": 3,
                        "initial_delay_seconds": 0.1,
                        "backoff_strategy": "fixed",
                    },
                    operation_name="test_op",
                    url="https://example.com",
                )

        assert mock_func.call_count == 3  # All attempts used

    async def test_backoff_delay_increases(self) -> None:
        """Test that backoff delay increases with exponential strategy."""
        mock_func = AsyncMock(
            return_value=ExecutionResult(success=False, error="503 error", status_code=503)
        )

        sleep_calls = []

        async def mock_sleep(delay: float) -> None:
            sleep_calls.append(delay)

        # Patch calculate_backoff to return deterministic values (no jitter)
        def deterministic_backoff(attempt: int, **kwargs: Any) -> float:
            # Simple exponential: 1, 2, 4
            return kwargs.get("initial_delay_seconds", 1.0) * (
                kwargs.get("backoff_multiplier", 2.0) ** (attempt - 1)
            )

        with (
            patch("crawler.services.executor_retry.asyncio.sleep", side_effect=mock_sleep),
            patch(
                "crawler.services.executor_retry.calculate_backoff",
                side_effect=deterministic_backoff,
            ),
        ):
            await execute_with_retry(
                func=mock_func,
                retry_config={
                    "max_attempts": 4,
                    "initial_delay_seconds": 1.0,
                    "backoff_strategy": "exponential",
                    "backoff_multiplier": 2.0,
                    "max_delay_seconds": 10.0,
                },
                operation_name="test_op",
                url="https://example.com",
            )

        # Should have 3 delays (max_attempts - 1)
        assert len(sleep_calls) == 3
        # With deterministic backoff, delays should be exactly: 1, 2, 4
        assert sleep_calls[0] == 1.0
        assert sleep_calls[1] == 2.0
        assert sleep_calls[2] == 4.0

    async def test_invalid_backoff_strategy_uses_default(self) -> None:
        """Test that invalid backoff strategy falls back to exponential."""
        mock_func = AsyncMock(
            side_effect=[
                ExecutionResult(success=False, error="503 error", status_code=503),
                ExecutionResult(success=True, content="success"),
            ]
        )

        with patch("crawler.services.executor_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await execute_with_retry(
                func=mock_func,
                retry_config={
                    "max_attempts": 3,
                    "backoff_strategy": "invalid_strategy",  # Invalid
                    "initial_delay_seconds": 0.1,
                },
                operation_name="test_op",
                url="https://example.com",
            )

        assert result.success is True
        assert mock_func.call_count == 2

    async def test_result_with_metadata_error_type(self) -> None:
        """Test classification of result with metadata error_type."""
        # Create result with metadata indicating retryable error
        mock_func = AsyncMock(
            side_effect=[
                ExecutionResult(
                    success=False,
                    error="Network error",
                    metadata={"error_type": "retryable"},
                ),
                ExecutionResult(success=True, content="success"),
            ]
        )

        with patch("crawler.services.executor_retry.asyncio.sleep", new_callable=AsyncMock):
            result = await execute_with_retry(
                func=mock_func,
                retry_config={
                    "max_attempts": 3,
                    "initial_delay_seconds": 0.1,
                    "backoff_strategy": "fixed",
                },
                operation_name="test_op",
                url="https://example.com",
            )

        assert result.success is True
        assert mock_func.call_count == 2

    async def test_result_with_metadata_permanent_error(self) -> None:
        """Test classification of result with metadata indicating permanent error."""
        mock_func = AsyncMock(
            return_value=ExecutionResult(
                success=False,
                error="Invalid request",
                metadata={"error_type": "permanent"},
            )
        )

        result = await execute_with_retry(
            func=mock_func,
            retry_config={"max_attempts": 3},
            operation_name="test_op",
            url="https://example.com",
        )

        assert result.success is False
        assert mock_func.call_count == 1  # No retry for permanent error
