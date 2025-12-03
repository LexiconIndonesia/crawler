"""Dependency validator for workflow step dependencies.

This module validates step dependencies, detects circular dependencies,
and determines the correct execution order using topological sorting.
"""

from __future__ import annotations

import re
from collections import defaultdict, deque
from typing import Any

from crawler.core.logging import get_logger

logger = get_logger(__name__)

# Pattern to match {{step_name}} or {{step_name.field}}
STEP_REFERENCE_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


class DependencyValidator:
    """Validates step dependencies and detects circular references.

    Uses topological sorting to determine execution order and detect cycles.
    """

    def __init__(self, steps: list[dict[str, Any]]):
        """Initialize dependency validator with workflow steps.

        Args:
            steps: List of step configurations (dicts with 'name' and 'input_from')
        """
        self.steps = steps
        self.step_names = {step["name"] for step in steps}
        self.dependency_graph: dict[str, list[str]] = defaultdict(list)
        self.in_degree: dict[str, int] = defaultdict(int)

    def validate(self) -> list[str]:
        """Validate dependencies and return execution order.

        Returns:
            List of step names in execution order

        Raises:
            ValueError: If validation fails (cycles, missing steps, etc.)
        """
        # Check for duplicate step names
        self._check_duplicate_names()

        # Build dependency graph
        self._build_graph()

        # Detect cycles and get execution order
        execution_order = self._topological_sort()

        logger.info(
            "dependency_validation_complete",
            total_steps=len(self.steps),
            execution_order=execution_order,
        )
        return execution_order

    def _check_duplicate_names(self) -> None:
        """Check for duplicate step names.

        Raises:
            ValueError: If duplicate step names are found
        """
        name_counts: dict[str, int] = defaultdict(int)
        for step in self.steps:
            name_counts[step["name"]] += 1

        duplicates = [name for name, count in name_counts.items() if count > 1]
        if duplicates:
            raise ValueError(
                f"Duplicate step names found: {', '.join(duplicates)}. "
                f"Each step must have a unique name."
            )

    def _build_graph(self) -> None:
        """Build dependency graph from step configurations.

        Checks input_from, skip_if, and run_only_if for dependencies.

        Raises:
            ValueError: If a step references a non-existent dependency
        """
        for step in self.steps:
            step_name = step["name"]

            # Initialize in-degree for all steps
            if step_name not in self.in_degree:
                self.in_degree[step_name] = 0

            # Collect all dependencies for this step
            dependencies = set()

            # 1. Parse input_from to extract dependency
            input_from = step.get("input_from")
            if input_from:
                dependencies.add(self._extract_dependency(input_from))

            # 2. Parse skip_if condition for dependencies
            skip_if = step.get("skip_if")
            if skip_if:
                dependencies.update(self._extract_condition_dependencies(skip_if))

            # 3. Parse run_only_if condition for dependencies
            run_only_if = step.get("run_only_if")
            if run_only_if:
                dependencies.update(self._extract_condition_dependencies(run_only_if))

            # Add edges for all dependencies
            for dependency in dependencies:
                # Validate dependency exists
                if dependency not in self.step_names:
                    raise ValueError(
                        f"Step '{step_name}' depends on non-existent step '{dependency}'. "
                        f"Available steps: {sorted(self.step_names)}"
                    )

                # Add edge: dependency -> step_name
                self.dependency_graph[dependency].append(step_name)
                self.in_degree[step_name] += 1

                logger.debug(
                    "dependency_added",
                    step=step_name,
                    depends_on=dependency,
                )

    def _extract_dependency(self, input_from: str) -> str:
        """Extract step name from input_from reference.

        Args:
            input_from: Input reference like "step_name.field" or "step_name"

        Returns:
            Step name (the part before the first dot)

        Example:
            >>> _extract_dependency("crawl_list.detail_urls")
            'crawl_list'
            >>> _extract_dependency("fetch_data")
            'fetch_data'
        """
        return input_from.split(".")[0]

    def _extract_condition_dependencies(self, condition: str) -> set[str]:
        """Extract step dependencies from condition string.

        Parses condition for {{step_name.field}} or {{step_name}} patterns.

        Args:
            condition: Condition string like "{{step1.count}} > 0"

        Returns:
            Set of step names referenced in condition

        Example:
            >>> _extract_condition_dependencies("{{step1.count}} > 0")
            {'step1'}
            >>> _extract_condition_dependencies("{{step1.status}} == 'success' and {{step2.ready}}")
            {'step1', 'step2'}
        """
        dependencies = set()
        matches = STEP_REFERENCE_PATTERN.findall(condition)

        for match in matches:
            # Extract step name (part before first dot)
            step_ref = match.strip()
            step_name = step_ref.split(".")[0]

            # Only add if it's a step reference (not a simple variable)
            # Simple variables don't have dots and are not step names
            if step_name in self.step_names:
                dependencies.add(step_name)

        return dependencies

    def _topological_sort(self) -> list[str]:
        """Perform topological sort to determine execution order.

        Uses Kahn's algorithm for topological sorting with cycle detection.

        Returns:
            List of step names in execution order

        Raises:
            ValueError: If a circular dependency is detected
        """
        # Create a working copy of in-degrees
        working_in_degree = self.in_degree.copy()

        # Find all steps with no dependencies (in-degree = 0)
        queue: deque[str] = deque(
            [step_name for step_name in self.step_names if working_in_degree[step_name] == 0]
        )

        execution_order: list[str] = []

        while queue:
            # Process step with no remaining dependencies
            current_step = queue.popleft()
            execution_order.append(current_step)

            # Reduce in-degree for dependent steps
            for dependent_step in self.dependency_graph[current_step]:
                working_in_degree[dependent_step] -= 1

                # If dependent step now has no dependencies, add to queue
                if working_in_degree[dependent_step] == 0:
                    queue.append(dependent_step)

        # Check if all steps were processed
        if len(execution_order) != len(self.steps):
            # Circular dependency detected
            unprocessed_steps = [step for step in self.step_names if step not in execution_order]
            cycle_info = self._detect_cycle(unprocessed_steps)
            raise ValueError(
                f"Circular dependency detected in workflow. "
                f"Steps involved in cycle: {', '.join(unprocessed_steps)}. "
                f"Cycle: {cycle_info}"
            )

        return execution_order

    def _detect_cycle(self, unprocessed_steps: list[str]) -> str:
        """Detect and describe the cycle in dependencies.

        Args:
            unprocessed_steps: Steps that couldn't be processed due to cycle

        Returns:
            Human-readable description of the cycle
        """
        # Try to find a cycle path using DFS
        visited: set[str] = set()
        rec_stack: list[str] = []

        def dfs(step: str) -> list[str] | None:
            """Depth-first search to find cycle."""
            visited.add(step)
            rec_stack.append(step)

            # Check all dependencies of current step
            for dependent in self.dependency_graph[step]:
                if dependent in rec_stack:
                    # Found cycle - return path from dependent to current
                    cycle_start = rec_stack.index(dependent)
                    return [*rec_stack[cycle_start:], dependent]

                if dependent not in visited:
                    cycle = dfs(dependent)
                    if cycle:
                        return cycle

            rec_stack.pop()
            return None

        # Try DFS from each unprocessed step
        for step in unprocessed_steps:
            if step not in visited:
                cycle = dfs(step)
                if cycle:
                    return " -> ".join(cycle)

        # Fallback if cycle detection fails
        return f"Unable to determine exact cycle path. Unprocessed steps: {unprocessed_steps}"

    def get_dependencies(self, step_name: str) -> list[str]:
        """Get direct dependencies for a step.

        Args:
            step_name: Name of the step

        Returns:
            List of step names that this step depends on (empty if none)
        """
        # Leverage the complete dependency graph built in _build_graph
        # which includes input_from, skip_if, and run_only_if dependencies
        return [dep for dep, dependents in self.dependency_graph.items() if step_name in dependents]

    def get_dependents(self, step_name: str) -> list[str]:
        """Get steps that depend on the given step.

        Args:
            step_name: Name of the step

        Returns:
            List of step names that depend on this step (empty if none)
        """
        return self.dependency_graph.get(step_name, [])

    def is_independent(self, step_name: str) -> bool:
        """Check if a step has no dependencies.

        Args:
            step_name: Name of the step

        Returns:
            True if step has no dependencies, False otherwise
        """
        return self.in_degree.get(step_name, 0) == 0
