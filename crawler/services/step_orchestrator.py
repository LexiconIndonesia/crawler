"""Step orchestrator for executing multi-step workflows.

This module provides the main orchestration engine that coordinates the execution
of multi-step workflows, handling dependencies, data flow, and error recovery.
"""

from __future__ import annotations

from typing import Any

from crawler.core.logging import get_logger
from crawler.services.condition_evaluator import ConditionEvaluator
from crawler.services.dependency_validator import DependencyValidator
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_execution_context import StepExecutionContext, StepResult
from crawler.services.step_executors import (
    APIExecutor,
    BrowserExecutor,
    HTTPExecutor,
)
from crawler.services.variable_resolver import VariableResolver

logger = get_logger(__name__)


class StepOrchestrator:
    """Orchestrates execution of multi-step workflows.

    The orchestrator:
    1. Validates dependencies and detects cycles
    2. Determines execution order
    3. Executes steps sequentially
    4. Resolves input dependencies and variables
    5. Passes data between steps
    6. Handles step skipping based on conditions
    7. Tracks results in execution context
    """

    def __init__(
        self,
        job_id: str,
        website_id: str,
        base_url: str,
        steps: list[dict[str, Any]],
        global_config: dict[str, Any] | None = None,
    ):
        """Initialize step orchestrator.

        Args:
            job_id: Crawl job ID
            website_id: Website ID
            base_url: Base URL for the website
            steps: List of step configurations
            global_config: Global configuration (timeout, headers, etc.)
        """
        self.job_id = job_id
        self.website_id = website_id
        self.base_url = base_url
        self.steps = steps
        self.global_config = global_config or {}

        # Initialize context
        self.context = StepExecutionContext(
            job_id=job_id,
            website_id=website_id,
            variables={"base_url": base_url},
        )

        # Initialize components
        self.selector_processor = SelectorProcessor()
        self.variable_resolver = VariableResolver(self.context)
        self.condition_evaluator = ConditionEvaluator(self.context)

        # Initialize executors (reuse clients for efficiency)
        self.http_executor = HTTPExecutor(selector_processor=self.selector_processor)
        self.api_executor = APIExecutor(selector_processor=self.selector_processor)
        self.browser_executor = BrowserExecutor(selector_processor=self.selector_processor)

        # Execution order (determined by dependency validation)
        self.execution_order: list[str] = []

    async def execute_workflow(self) -> StepExecutionContext:
        """Execute the complete workflow.

        Returns:
            Execution context with all step results

        Raises:
            ValueError: If dependency validation fails
        """
        try:
            # Step 1: Validate dependencies and get execution order
            logger.info(
                "workflow_starting",
                job_id=self.job_id,
                total_steps=len(self.steps),
            )
            validator = DependencyValidator(self.steps)
            self.execution_order = validator.validate()

            logger.info(
                "dependency_validation_complete",
                job_id=self.job_id,
                execution_order=self.execution_order,
            )

            # Step 2: Execute steps in order
            for step_name in self.execution_order:
                step_config = self._get_step_config(step_name)
                if not step_config:
                    logger.error("step_not_found", step_name=step_name)
                    continue

                # Execute step
                await self._execute_step(step_config)

            logger.info(
                "workflow_completed",
                job_id=self.job_id,
                successful_steps=len(self.context.get_successful_steps()),
                failed_steps=len(self.context.get_failed_steps()),
            )

            return self.context

        finally:
            # Clean up resources
            await self._cleanup()

    async def _execute_step(self, step_config: dict[str, Any]) -> None:
        """Execute a single step.

        Args:
            step_config: Step configuration
        """
        step_name = step_config["name"]

        try:
            logger.info("step_starting", job_id=self.job_id, step_name=step_name)

            # Step 1: Check if step should be skipped
            if await self._should_skip_step(step_config):
                logger.info("step_skipped", step_name=step_name)
                self.context.add_result(
                    StepResult(
                        step_name=step_name,
                        metadata={"skipped": True},
                    )
                )
                return

            # Step 2: Resolve input URL(s)
            urls = await self._resolve_step_urls(step_config)
            if not urls:
                logger.warning("step_no_urls", step_name=step_name)
                self.context.add_result(
                    StepResult(
                        step_name=step_name,
                        error="No URLs to process",
                    )
                )
                return

            # Step 3: Execute step for each URL
            # Convert single URL to list for uniform processing
            url_list = urls if isinstance(urls, list) else [urls]

            # Step 4: Get executor and execute for all URLs
            executor = self._get_executor(step_config)
            merged_config = self._merge_config(step_config)
            selectors = step_config.get("selectors", {})

            # Execute for each URL and collect results
            all_results = []
            all_extracted_data = []
            errors = []
            last_status_code = None
            last_content = None

            for idx, url in enumerate(url_list):
                logger.debug(
                    "executing_url",
                    step_name=step_name,
                    url_index=idx,
                    total_urls=len(url_list),
                    url=url,
                )

                result = await executor.execute(url, merged_config, selectors)
                all_results.append(result)

                if result.success:
                    # Collect extracted data
                    all_extracted_data.append(result.extracted_data)
                    last_status_code = result.status_code
                    last_content = result.content
                else:
                    # Track errors
                    errors.append(f"URL {idx} ({url}): {result.error}")

            # Step 5: Aggregate results and store in context
            if len(url_list) == 1:
                # Single URL: store as-is
                aggregated_data = all_extracted_data[0] if all_extracted_data else {}
            else:
                # Multiple URLs: store as array under 'items' key
                aggregated_data = {"items": all_extracted_data}

            # Determine overall success
            success_count = sum(1 for r in all_results if r.success)
            overall_error = (
                None if success_count > 0 else ("; ".join(errors) if errors else "All URLs failed")
            )

            step_result = StepResult(
                step_name=step_name,
                status_code=last_status_code,
                content=last_content,
                extracted_data=aggregated_data,
                metadata={
                    "total_urls": len(url_list),
                    "successful_urls": success_count,
                    "failed_urls": len(url_list) - success_count,
                    "errors": errors if errors else None,
                },
                error=overall_error,
            )
            self.context.add_result(step_result)

            if step_result.success:
                logger.info(
                    "step_completed",
                    step_name=step_name,
                    total_urls=len(url_list),
                    successful_urls=success_count,
                    extracted_fields=len(aggregated_data),
                )
            else:
                logger.error(
                    "step_failed",
                    step_name=step_name,
                    error=step_result.error,
                    failed_urls=len(url_list) - success_count,
                )

        except Exception as e:
            logger.error(
                "step_execution_error",
                step_name=step_name,
                error=str(e),
                exc_info=True,
            )
            self.context.add_result(
                StepResult(
                    step_name=step_name,
                    error=f"Execution error: {e}",
                )
            )

    async def _should_skip_step(self, step_config: dict[str, Any]) -> bool:
        """Check if step should be skipped based on conditions.

        Args:
            step_config: Step configuration

        Returns:
            True if step should be skipped, False otherwise

        Supports two condition types:
        - skip_if: Skip step if condition is true
        - run_only_if: Skip step if condition is false

        Example conditions:
        - "{{previous_step.count}} == 0" - Skip if count is zero
        - "{{step1.status}} == 'failed'" - Skip if step1 failed
        - "{{step1.items}} empty" - Skip if items list is empty
        """
        step_name = step_config["name"]

        # Check skip_if condition
        skip_if = step_config.get("skip_if")
        if skip_if:
            logger.debug(
                "evaluating_skip_if",
                step_name=step_name,
                condition=skip_if,
            )
            should_skip = self.condition_evaluator.evaluate(skip_if)
            if should_skip:
                logger.info(
                    "skip_condition_met",
                    step_name=step_name,
                    condition=skip_if,
                )
            return should_skip

        # Check run_only_if condition
        run_only_if = step_config.get("run_only_if")
        if run_only_if:
            logger.debug(
                "evaluating_run_only_if",
                step_name=step_name,
                condition=run_only_if,
            )
            should_run = self.condition_evaluator.evaluate(run_only_if)
            if not should_run:
                logger.info(
                    "run_only_if_condition_not_met",
                    step_name=step_name,
                    condition=run_only_if,
                )
            return not should_run

        # No conditions configured, don't skip
        return False

    async def _resolve_step_urls(self, step_config: dict[str, Any]) -> list[str] | str:
        """Resolve URL(s) for step execution.

        Args:
            step_config: Step configuration

        Returns:
            URL string or list of URLs to process

        Raises:
            ValueError: If URL resolution fails
        """
        step_name = step_config["name"]
        input_from = step_config.get("input_from")

        # Case 1: No input dependency - use base URL or configured URL
        if not input_from:
            configured_url = step_config.get("config", {}).get("url")
            if configured_url:
                return self.variable_resolver.resolve(configured_url)
            return self.base_url

        # Case 2: Input from previous step
        try:
            # Extract step name and field path
            dependency_step = input_from.split(".")[0]
            field_path = ".".join(input_from.split(".")[1:]) if "." in input_from else None

            # Check if dependency step executed successfully
            if not self.context.has_step_result(dependency_step):
                raise ValueError(
                    f"Step '{step_name}' depends on '{dependency_step}' which has not executed"
                )

            dependency_result = self.context.get_result(dependency_step)
            if not dependency_result or not dependency_result.success:
                raise ValueError(f"Step '{step_name}' depends on '{dependency_step}' which failed")

            # Get output from dependency step
            dependency_output = self.context.get_step_output(dependency_step)

            # Navigate to specified field
            if field_path:
                value = self._navigate_field_path(dependency_output, field_path)
            else:
                value = dependency_output

            # Return URLs
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                return value
            if isinstance(value, dict) and "url" in value:
                url_value = value["url"]
                if isinstance(url_value, (str, list)):
                    return url_value
                raise ValueError(
                    f"URL field has invalid type {type(url_value).__name__}, "
                    f"expected string or list"
                )

            raise ValueError(
                f"Could not extract URL from input_from '{input_from}'. "
                f"Expected string or list, got {type(value).__name__}"
            )

        except Exception as e:
            logger.error(
                "url_resolution_error",
                step_name=step_name,
                input_from=input_from,
                error=str(e),
            )
            raise ValueError(f"Failed to resolve URLs for step '{step_name}': {e}") from e

    def _navigate_field_path(self, data: dict[str, Any], field_path: str) -> Any:
        """Navigate a field path in data dictionary.

        Args:
            data: Data dictionary
            field_path: Dot-separated field path

        Returns:
            Value at field path
        """
        parts = field_path.split(".")
        current: Any = data

        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                current = current[int(part)]
            else:
                return None

        return current

    def _get_executor(
        self, step_config: dict[str, Any]
    ) -> HTTPExecutor | BrowserExecutor | APIExecutor:
        """Get appropriate executor for step method.

        Args:
            step_config: Step configuration

        Returns:
            Executor instance based on step method

        Raises:
            ValueError: If method is not supported
        """
        method = step_config.get("method", "http").lower()

        if method == "http":
            return self.http_executor
        elif method == "browser":
            return self.browser_executor
        elif method == "api":
            return self.api_executor
        else:
            raise ValueError(f"Unsupported method: {method}")

    def _merge_config(self, step_config: dict[str, Any]) -> dict[str, Any]:
        """Merge step config with global config.

        Args:
            step_config: Step-specific configuration

        Returns:
            Merged configuration (step config takes precedence)
        """
        merged = self.global_config.copy()
        step_specific = step_config.get("config", {})
        merged.update(step_specific)

        # Add method from step config
        if "method" in step_config:
            merged["method"] = step_config["method"]

        # Add browser_type if specified
        if "browser_type" in step_config:
            merged["browser_type"] = step_config["browser_type"]

        return merged

    def _get_step_config(self, step_name: str) -> dict[str, Any] | None:
        """Get step configuration by name.

        Args:
            step_name: Name of the step

        Returns:
            Step configuration or None if not found
        """
        for step in self.steps:
            if step["name"] == step_name:
                return step
        return None

    async def _cleanup(self) -> None:
        """Clean up executor resources."""
        try:
            await self.http_executor.cleanup()
            await self.api_executor.cleanup()
            await self.browser_executor.cleanup()
            logger.debug("orchestrator_cleanup_complete")
        except Exception as e:
            logger.error("orchestrator_cleanup_error", error=str(e))
