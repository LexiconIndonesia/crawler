"""Base step executor interface.

Defines the interface that all step executors must implement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from crawler.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ExecutionResult:
    """Result from executing a step.

    Attributes:
        success: Whether execution was successful
        status_code: HTTP status code (if applicable)
        content: Raw content (HTML, JSON, text)
        extracted_data: Data extracted using selectors
        metadata: Additional metadata (headers, timing, errors)
        error: Error message if execution failed
    """

    success: bool
    status_code: int | None = None
    content: str | dict[str, Any] | None = None
    extracted_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class BaseStepExecutor(ABC):
    """Abstract base class for step executors.

    All step executors (HTTP, Browser, API) must implement this interface.
    """

    @abstractmethod
    async def execute(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute a step and return the result.

        Args:
            url: Target URL to execute step against
            step_config: Step configuration (timeout, headers, etc.)
            selectors: Selectors to apply for data extraction

        Returns:
            ExecutionResult with content and extracted data

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError("Subclass must implement execute()")

    @abstractmethod
    async def cleanup(self) -> None:
        """Clean up resources (connections, browsers, etc.).

        Raises:
            NotImplementedError: Must be implemented by subclass
        """
        raise NotImplementedError("Subclass must implement cleanup()")

    def _create_error_result(self, error_message: str, **kwargs: Any) -> ExecutionResult:
        """Create an error execution result.

        Args:
            error_message: Error description
            **kwargs: Additional metadata to include

        Returns:
            ExecutionResult with error
        """
        logger.error("step_execution_error", error=error_message, **kwargs)
        return ExecutionResult(
            success=False,
            error=error_message,
            metadata=kwargs,
        )

    def _create_success_result(
        self,
        content: str | dict[str, Any],
        extracted_data: dict[str, Any],
        status_code: int | None = None,
        **metadata: Any,
    ) -> ExecutionResult:
        """Create a successful execution result.

        Args:
            content: Raw content retrieved
            extracted_data: Data extracted using selectors
            status_code: HTTP status code
            **metadata: Additional metadata

        Returns:
            ExecutionResult with content and extracted data
        """
        return ExecutionResult(
            success=True,
            status_code=status_code,
            content=content,
            extracted_data=extracted_data,
            metadata=metadata,
        )
