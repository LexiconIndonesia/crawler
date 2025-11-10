"""Step execution context for tracking state between workflow steps.

This module provides the context management for multi-step workflow execution,
storing inputs, outputs, and intermediate results for each step.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crawler.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class StepResult:
    """Result from executing a single step.

    Attributes:
        step_name: Name of the executed step
        status_code: HTTP status code (if applicable)
        content: Response content (HTML, JSON, text)
        extracted_data: Data extracted using selectors
        metadata: Additional metadata (headers, timing, etc)
        error: Error message if step failed
    """

    step_name: str
    status_code: int | None = None
    content: str | dict[str, Any] | None = None
    extracted_data: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    @property
    def success(self) -> bool:
        """Check if step executed successfully."""
        return self.error is None and (self.status_code is None or 200 <= self.status_code < 300)


@dataclass
class StepExecutionContext:
    """Context for tracking state during multi-step workflow execution.

    This context is passed between steps and accumulates results from each step.
    It provides methods to store and retrieve step outputs for dependency resolution.

    Attributes:
        job_id: ID of the crawl job
        website_id: ID of the website being crawled
        variables: Global variables available to all steps
        step_results: Results from executed steps (keyed by step name)
        execution_order: Order in which steps were executed
        metadata: Additional workflow-level metadata (cancellation status, etc.)
    """

    job_id: str
    website_id: str
    variables: dict[str, Any] = field(default_factory=dict)
    step_results: dict[str, StepResult] = field(default_factory=dict)
    execution_order: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def add_result(self, result: StepResult) -> None:
        """Add a step result to the context.

        Args:
            result: The step result to add
        """
        self.step_results[result.step_name] = result
        self.execution_order.append(result.step_name)
        logger.debug(
            "step_result_added",
            job_id=self.job_id,
            step_name=result.step_name,
            success=result.success,
        )

    def get_result(self, step_name: str) -> StepResult | None:
        """Get result from a previous step.

        Args:
            step_name: Name of the step to retrieve

        Returns:
            The step result or None if not found
        """
        return self.step_results.get(step_name)

    def get_step_output(self, step_name: str) -> dict[str, Any]:
        """Get the extracted data output from a previous step.

        Args:
            step_name: Name of the step to retrieve output from

        Returns:
            The extracted data from the step, or empty dict if not found
        """
        result = self.get_result(step_name)
        if result and result.success:
            return result.extracted_data
        return {}

    def set_variable(self, key: str, value: Any) -> None:
        """Set a global variable in the context.

        Args:
            key: Variable name
            value: Variable value
        """
        self.variables[key] = value
        logger.debug("context_variable_set", job_id=self.job_id, key=key)

    def get_variable(self, key: str, default: Any = None) -> Any:
        """Get a global variable from the context.

        Args:
            key: Variable name
            default: Default value if variable not found

        Returns:
            The variable value or default
        """
        return self.variables.get(key, default)

    def has_step_result(self, step_name: str) -> bool:
        """Check if a step has been executed and has a result.

        Args:
            step_name: Name of the step to check

        Returns:
            True if step result exists, False otherwise
        """
        return step_name in self.step_results

    def get_failed_steps(self) -> list[str]:
        """Get list of steps that failed during execution.

        Returns:
            List of step names that failed
        """
        return [name for name, result in self.step_results.items() if not result.success]

    def get_successful_steps(self) -> list[str]:
        """Get list of steps that succeeded during execution.

        Returns:
            List of step names that succeeded
        """
        return [name for name, result in self.step_results.items() if result.success]

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary for serialization.

        Returns:
            Dictionary representation of the context
        """
        return {
            "job_id": self.job_id,
            "website_id": self.website_id,
            "variables": self.variables,
            "step_results": {
                name: {
                    "step_name": result.step_name,
                    "status_code": result.status_code,
                    "extracted_data": result.extracted_data,
                    "metadata": result.metadata,
                    "error": result.error,
                    "success": result.success,
                }
                for name, result in self.step_results.items()
            },
            "execution_order": self.execution_order,
            "failed_steps": self.get_failed_steps(),
            "successful_steps": self.get_successful_steps(),
            "metadata": self.metadata,
        }
