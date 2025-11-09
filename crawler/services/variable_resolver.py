"""Variable resolver for dynamic value substitution in workflow steps.

This module handles resolving variables like {{var_name}} or {{step_name.field}}
in URLs, headers, and other step configurations.
"""

from __future__ import annotations

import re
from typing import Any

from crawler.core.logging import get_logger
from crawler.services.step_execution_context import StepExecutionContext

logger = get_logger(__name__)

# Pattern to match variables: {{variable}} or {{step.field}} or {{step.nested.field}}
VARIABLE_PATTERN = re.compile(r"\{\{([^}]+)\}\}")


class VariableResolver:
    """Resolves variables in strings using execution context.

    Supports:
    - Simple variables: {{var_name}}
    - Step outputs: {{step_name.field}}
    - Nested fields: {{step_name.field.nested}}
    - Context variables: {{variable_name}}
    """

    def __init__(self, context: StepExecutionContext):
        """Initialize resolver with execution context.

        Args:
            context: The execution context containing variables and step results
        """
        self.context = context

    def resolve(self, template: str | Any) -> str | Any:
        """Resolve variables in a template string.

        Args:
            template: String template with {{variable}} placeholders, or any other type

        Returns:
            String with variables resolved, or original value if not a string

        Raises:
            ValueError: If variable reference is invalid or not found
        """
        if not isinstance(template, str):
            return template

        # Find all variable references in the template
        matches = VARIABLE_PATTERN.findall(template)
        if not matches:
            return template

        result = template
        for match in matches:
            placeholder = f"{{{{{match}}}}}"
            value = self._resolve_reference(match.strip())
            result = result.replace(placeholder, str(value))

        logger.debug(
            "variable_resolved",
            job_id=self.context.job_id,
            template=template,
            result=result,
        )
        return result

    def resolve_dict(self, data: dict[str, Any]) -> dict[str, Any]:
        """Resolve variables in all values of a dictionary.

        Args:
            data: Dictionary with potential variable references

        Returns:
            Dictionary with resolved values
        """
        resolved = {}
        for key, value in data.items():
            if isinstance(value, str):
                resolved[key] = self.resolve(value)
            elif isinstance(value, dict):
                resolved[key] = self.resolve_dict(value)
            elif isinstance(value, list):
                resolved[key] = self.resolve_list(value)
            else:
                resolved[key] = value
        return resolved

    def resolve_list(self, data: list[Any]) -> list[Any]:
        """Resolve variables in all items of a list.

        Args:
            data: List with potential variable references

        Returns:
            List with resolved values
        """
        resolved = []
        for item in data:
            if isinstance(item, str):
                resolved.append(self.resolve(item))
            elif isinstance(item, dict):
                resolved.append(self.resolve_dict(item))
            elif isinstance(item, list):
                resolved.append(self.resolve_list(item))
            else:
                resolved.append(item)
        return resolved

    def _resolve_reference(self, reference: str) -> Any:
        """Resolve a single variable reference.

        Args:
            reference: Variable reference (e.g., "var_name" or "step.field.nested")

        Returns:
            The resolved value

        Raises:
            ValueError: If reference is invalid or not found
        """
        parts = reference.split(".")

        # Single part: context variable
        if len(parts) == 1:
            var_name = parts[0]
            if var_name in self.context.variables:
                return self.context.variables[var_name]
            raise ValueError(
                f"Variable '{var_name}' not found in context. "
                f"Available: {list(self.context.variables.keys())}"
            )

        # Multiple parts: step output reference
        step_name = parts[0]
        field_path = parts[1:]

        # Check if step has been executed
        if not self.context.has_step_result(step_name):
            raise ValueError(
                f"Step '{step_name}' has not been executed yet or not found. "
                f"Executed steps: {self.context.execution_order}"
            )

        # Get step output
        step_output = self.context.get_step_output(step_name)
        if not step_output:
            raise ValueError(f"Step '{step_name}' has no output data (step may have failed)")

        # Navigate nested fields
        value = step_output
        for field in field_path:
            if isinstance(value, dict):
                if field not in value:
                    raise ValueError(
                        f"Field '{field}' not found in step '{step_name}' output. "
                        f"Available fields: {list(value.keys())}"
                    )
                value = value[field]
            elif isinstance(value, list):
                # Support array indexing like {{step.items.0}}
                try:
                    index = int(field)
                    value = value[index]
                except (ValueError, IndexError) as e:
                    raise ValueError(
                        f"Invalid array index '{field}' for step '{step_name}' output"
                    ) from e
            else:
                raise ValueError(
                    f"Cannot access field '{field}' on non-dict/list value "
                    f"in step '{step_name}' output"
                )

        return value

    def has_variables(self, template: str) -> bool:
        """Check if a template contains variable placeholders.

        Args:
            template: String template to check

        Returns:
            True if template contains {{...}} patterns, False otherwise
        """
        if not isinstance(template, str):
            return False
        return bool(VARIABLE_PATTERN.search(template))

    def extract_variable_names(self, template: str) -> list[str]:
        """Extract all variable names from a template.

        Args:
            template: String template to analyze

        Returns:
            List of variable names found in template
        """
        if not isinstance(template, str):
            return []
        return VARIABLE_PATTERN.findall(template)
