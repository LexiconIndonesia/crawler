"""Step orchestrator for executing multi-step workflows.

This module provides the main orchestration engine that coordinates the execution
of multi-step workflows, handling dependencies, data flow, and error recovery.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any

from crawler.core.logging import get_logger
from crawler.services.condition_evaluator import ConditionEvaluator
from crawler.services.dependency_validator import DependencyValidator
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_execution_context import StepExecutionContext, StepResult
from crawler.services.step_validator import StepValidationError, StepValidator
from crawler.services.step_executors import (
    APIExecutor,
    BrowserExecutor,
    CrawlExecutor,
    HTTPExecutor,
    ScrapeExecutor,
)
from crawler.services.step_executors.base import ExecutionResult
from crawler.services.variable_resolver import VariableResolver

if TYPE_CHECKING:
    from crawler.services.redis_cache import JobCancellationFlag

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
        cancellation_flag: JobCancellationFlag | None = None,
    ):
        """Initialize step orchestrator.

        Args:
            job_id: Crawl job ID
            website_id: Website ID
            base_url: Base URL for the website
            steps: List of step configurations
            global_config: Global configuration (timeout, headers, etc.)
            cancellation_flag: Optional cancellation flag for mid-execution cancellation
        """
        self.job_id = job_id
        self.website_id = website_id
        self.base_url = base_url
        self.steps = steps
        self.global_config = global_config or {}
        self.cancellation_flag = cancellation_flag

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
        self.step_validator = StepValidator()

        # Initialize executors (reuse clients for efficiency)
        self.http_executor = HTTPExecutor(selector_processor=self.selector_processor)
        self.api_executor = APIExecutor(selector_processor=self.selector_processor)
        self.browser_executor = BrowserExecutor(selector_processor=self.selector_processor)
        self.crawl_executor = CrawlExecutor(
            http_executor=self.http_executor,
            api_executor=self.api_executor,
            browser_executor=self.browser_executor,
            selector_processor=self.selector_processor,
        )
        self.scrape_executor = ScrapeExecutor(
            http_executor=self.http_executor,
            api_executor=self.api_executor,
            browser_executor=self.browser_executor,
            selector_processor=self.selector_processor,
        )

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
                # Check for cancellation between steps
                if await self._check_cancellation():
                    logger.info(
                        "workflow_cancelled",
                        job_id=self.job_id,
                        completed_steps=len(self.context.step_results),
                        total_steps=len(self.steps),
                    )
                    # Mark context as cancelled
                    self.context.metadata["cancelled"] = True
                    return self.context

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
        """Execute a single step with timeout enforcement.

        Args:
            step_config: Step configuration
        """
        step_name = step_config["name"]

        try:
            logger.info("step_starting", job_id=self.job_id, step_name=step_name)

            # Step 1: Check if step should be skipped
            if self._should_skip_step(step_config):
                logger.info("step_skipped", step_name=step_name)
                self.context.add_result(
                    StepResult(
                        step_name=step_name,
                        metadata={"skipped": True},
                    )
                )
                return

            # Step 2: Resolve input URL(s)
            urls = self._resolve_step_urls(step_config)
            if not urls:
                logger.warning("step_no_urls", step_name=step_name)
                self.context.add_result(
                    StepResult(
                        step_name=step_name,
                        error="No URLs to process",
                    )
                )
                return

            # Step 3: Validate input before execution
            step_type = step_config.get("type", "").lower()
            try:
                self.step_validator.validate_input(
                    step_name=step_name,
                    step_type=step_type,
                    input_data=urls,
                    strict=True,  # Fail fast on invalid input
                )
            except StepValidationError as e:
                logger.error(
                    "step_input_validation_failed",
                    step_name=step_name,
                    errors=e.errors,
                )
                self.context.add_result(
                    StepResult(
                        step_name=step_name,
                        error=f"Input validation failed: {e}",
                        metadata={"validation_errors": e.errors},
                    )
                )
                return

            # Step 4: Get executor and merged config
            executor = self._get_executor(step_config)
            merged_config = self.variable_resolver.resolve_dict(self._merge_config(step_config))
            selectors = step_config.get("selectors", {})

            # Step 5: Get timeout from config (default: 30 seconds)
            timeout_seconds = merged_config.get("timeout", 30)

            # Step 5: Execute step with timeout enforcement and timing
            start_time = time.time()
            try:
                # Wrap execution with asyncio.wait_for for timeout enforcement
                result = await asyncio.wait_for(
                    self._execute_with_executor(executor, urls, merged_config, selectors),
                    timeout=timeout_seconds,
                )
                execution_time = time.time() - start_time

                # Add execution time to result metadata
                if result.metadata is None:
                    result.metadata = {}
                result.metadata["execution_time_seconds"] = round(execution_time, 3)
                result.metadata["timeout_configured"] = timeout_seconds

            except TimeoutError:
                # Step timeout exceeded
                execution_time = time.time() - start_time
                logger.error(
                    "step_timeout",
                    step_name=step_name,
                    timeout_seconds=timeout_seconds,
                    execution_time_seconds=round(execution_time, 3),
                    job_id=self.job_id,
                )
                self.context.add_result(
                    StepResult(
                        step_name=step_name,
                        error=f"Step execution timeout after {timeout_seconds}s",
                        metadata={
                            "timeout": True,
                            "timeout_seconds": timeout_seconds,
                            "execution_time_seconds": round(execution_time, 3),
                        },
                    )
                )
                return

            # Step 6: Validate output after execution
            try:
                self.step_validator.validate_output(
                    step_name=step_name,
                    step_type=step_type,
                    extracted_data=result.extracted_data,
                    metadata=result.metadata,
                    strict=False,  # Log warnings but don't fail on invalid output
                )
            except StepValidationError as e:
                # This should not happen with strict=False, but handle just in case
                logger.warning(
                    "step_output_validation_failed",
                    step_name=step_name,
                    errors=e.errors,
                )
                # Add validation warnings to metadata
                if result.metadata is None:
                    result.metadata = {}
                result.metadata["output_validation_warnings"] = e.errors

            # Step 7: Store result in context
            step_result = StepResult(
                step_name=step_name,
                status_code=result.status_code,
                content=result.content,
                extracted_data=result.extracted_data,
                metadata=result.metadata,
                error=result.error,
            )
            self.context.add_result(step_result)

            if step_result.success:
                logger.info(
                    "step_completed",
                    step_name=step_name,
                    total_urls=step_result.metadata.get("total_urls", 0),
                    successful_urls=step_result.metadata.get("successful_urls", 0),
                    extracted_fields=len(step_result.extracted_data),
                    execution_time_seconds=step_result.metadata.get("execution_time_seconds"),
                    timeout_configured=step_result.metadata.get("timeout_configured"),
                )
            else:
                logger.error(
                    "step_failed",
                    step_name=step_name,
                    error=step_result.error,
                    failed_urls=step_result.metadata.get("failed_urls", 0),
                    execution_time_seconds=step_result.metadata.get("execution_time_seconds"),
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

    async def _execute_with_executor(
        self,
        executor: HTTPExecutor | BrowserExecutor | APIExecutor | CrawlExecutor | ScrapeExecutor,
        urls: str | list[str],
        merged_config: dict[str, Any],
        selectors: dict[str, Any],
    ) -> ExecutionResult:
        """Execute step with the appropriate executor.

        Args:
            executor: Executor instance
            urls: URL(s) to process
            merged_config: Merged configuration
            selectors: Selectors for data extraction

        Returns:
            ExecutionResult from executor
        """
        # ScrapeExecutor and CrawlExecutor can handle str | list[str]
        # Base executors (HTTP, API, Browser) require iteration
        if isinstance(executor, (ScrapeExecutor, CrawlExecutor)):
            # Executors that handle str | list[str]: pass URLs as-is
            return await executor.execute(urls, merged_config, selectors)
        else:
            # Base executors (HTTP, API, Browser): iterate over URLs
            urls_list = [urls] if isinstance(urls, str) else urls
            all_results: list[ExecutionResult] = []

            for url in urls_list:
                single_result = await executor.execute(url, merged_config, selectors)
                all_results.append(single_result)

            # Aggregate ExecutionResults into a single ExecutionResult
            return self._aggregate_execution_results(all_results)

    def _should_skip_step(self, step_config: dict[str, Any]) -> bool:
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

    def _resolve_step_urls(self, step_config: dict[str, Any]) -> list[str] | str:
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
    ) -> HTTPExecutor | BrowserExecutor | APIExecutor | CrawlExecutor | ScrapeExecutor:
        """Get appropriate executor for step type and method.

        Args:
            step_config: Step configuration

        Returns:
            Executor instance based on step type and method

        Raises:
            ValueError: If method is not supported

        For crawl steps, returns CrawlExecutor which handles pagination
        and URL aggregation. For scrape steps, returns ScrapeExecutor which
        handles batch processing and content extraction.

        If no type is specified, falls back to method-specific executors
        for backward compatibility.
        """
        step_type = step_config.get("type", "").lower()

        # Use CrawlExecutor for crawl-type steps
        if step_type == "crawl":
            return self.crawl_executor

        # Use ScrapeExecutor for scrape-type steps
        if step_type == "scrape":
            return self.scrape_executor

        # Fallback to method-specific executors for backward compatibility
        # (when no type is specified)
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

    def _aggregate_execution_results(self, results: list[ExecutionResult]) -> ExecutionResult:
        """Aggregate multiple ExecutionResults into a single result.

        Args:
            results: List of individual ExecutionResults to aggregate

        Returns:
            Aggregated ExecutionResult with combined data and metadata

        Combines results from multiple URL executions into a single result
        for non-batch-aware executors (HTTP, API, Browser, Crawl).

        Content handling:
            - All strings: Joined with double newlines
            - Single item: Returned as-is
            - Mixed types: Returned as dict with numeric string keys (e.g., {"0": ..., "1": ...})

        Error handling:
            - Success: At least one URL succeeded
            - error field: Set only if ALL URLs failed (complete failure)
            - metadata["errors"]: Always present, contains all error messages (empty list if none)
        """
        # Guard: no results
        if not results:
            return ExecutionResult(
                success=False,
                error="No results to aggregate",
            )

        # Guard: single result
        if len(results) == 1:
            return results[0]

        # Aggregate multiple results
        all_extracted_data: dict[str, Any] = {}
        all_content_parts: list[str | dict[str, Any]] = []
        errors: list[str] = []
        successful_count = 0
        failed_count = 0

        for result in results:
            if result.success:
                successful_count += 1
                if result.extracted_data:
                    # Merge extracted data - accumulate values in lists
                    for key, value in result.extracted_data.items():
                        if key not in all_extracted_data:
                            all_extracted_data[key] = []
                        # Ensure value is in a list
                        values = value if isinstance(value, list) else [value]
                        all_extracted_data[key].extend(values)
                if result.content:
                    all_content_parts.append(result.content)
            else:
                failed_count += 1
                if result.error:
                    errors.append(result.error)

        # Determine overall success (at least one success)
        overall_success = successful_count > 0

        # Only set error if ALL URLs failed (complete failure)
        # For partial failures, errors go in metadata only
        overall_error: str | None = None
        if errors and failed_count == len(results):
            # Complete failure - set error
            overall_error = "; ".join(errors)

        # Combine content - if all are strings, join them; otherwise keep as list
        combined_content: str | dict[str, Any] | None = None
        if all_content_parts:
            if all(isinstance(c, str) for c in all_content_parts):
                combined_content = "\n\n".join(str(c) for c in all_content_parts)
            elif len(all_content_parts) == 1:
                combined_content = all_content_parts[0]
            else:
                # Mixed types - keep as dict with index
                combined_content = {str(i): c for i, c in enumerate(all_content_parts)}

        return ExecutionResult(
            success=overall_success,
            status_code=200 if overall_success else 500,
            content=combined_content,
            extracted_data=all_extracted_data if all_extracted_data else {},
            metadata={
                "total_urls": len(results),
                "successful_urls": successful_count,
                "failed_urls": failed_count,
                "aggregated": True,
                "errors": errors,  # Always include errors (empty list if none)
            },
            error=overall_error,
        )

    async def _check_cancellation(self) -> bool:
        """Check if workflow should be cancelled.

        Returns:
            True if workflow is cancelled, False otherwise

        Uses guard pattern to return early when cancellation is not configured.
        """
        # Guard: no cancellation flag configured
        if not self.cancellation_flag:
            return False

        # Check cancellation status
        is_cancelled = await self.cancellation_flag.is_cancelled(self.job_id)
        return is_cancelled

    async def _cleanup(self) -> None:
        """Clean up executor resources."""
        try:
            await self.http_executor.cleanup()
            await self.api_executor.cleanup()
            await self.browser_executor.cleanup()
            await self.crawl_executor.cleanup()
            await self.scrape_executor.cleanup()
            logger.debug("orchestrator_cleanup_complete")
        except Exception as e:
            logger.error("orchestrator_cleanup_error", error=str(e))
