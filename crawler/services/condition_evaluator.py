"""Condition evaluator for step execution control.

Evaluates conditions for determining whether steps should be skipped or executed.
"""

from __future__ import annotations

from typing import Any

from crawler.core.logging import get_logger
from crawler.services.step_execution_context import StepExecutionContext
from crawler.services.variable_resolver import VariableResolver

logger = get_logger(__name__)

# Type alias for values that can be compared in conditions
ComparableValue = str | int | float | bool | None


class ConditionEvaluator:
    """Evaluates conditions for step execution control.

    Supports basic comparison operators:
    - == (equals)
    - != (not equals)
    - > (greater than)
    - < (less than)
    - >= (greater than or equal)
    - <= (less than or equal)

    Also supports special checks:
    - exists (checks if variable/field exists)
    - empty (checks if list/dict is empty)
    - !empty (checks if list/dict is not empty)
    """

    def __init__(self, context: StepExecutionContext):
        """Initialize condition evaluator.

        Args:
            context: Execution context with variables and step results
        """
        self.context = context
        self.resolver = VariableResolver(context)

    def evaluate(self, condition: str) -> bool:
        """Evaluate a condition string.

        Args:
            condition: Condition string to evaluate

        Returns:
            True if condition is met, False otherwise

        Example:
            >>> evaluator.evaluate("{{step1.count}} > 0")
            True
            >>> evaluator.evaluate("{{step1.status}} == 'success'")
            False
        """
        try:
            condition = condition.strip()

            # Check for special operators
            if " exists" in condition:
                return self._evaluate_exists(condition)
            if " empty" in condition or " !empty" in condition:
                return self._evaluate_empty(condition)

            # Parse comparison operators
            for operator in ["==", "!=", ">=", "<=", ">", "<"]:
                if operator in condition:
                    return self._evaluate_comparison(condition, operator)

            # If no operator found, treat as boolean check
            return self._evaluate_boolean(condition)

        except Exception as e:
            logger.error(
                "condition_evaluation_error",
                condition=condition,
                error=str(e),
                exc_info=True,
            )
            # On error, default to not skipping (safer to execute)
            return False

    def _evaluate_comparison(self, condition: str, operator: str) -> bool:
        """Evaluate a comparison condition.

        Args:
            condition: Condition string
            operator: Comparison operator

        Returns:
            Boolean result of comparison
        """
        parts = condition.split(operator, 1)
        if len(parts) != 2:
            logger.warning("invalid_comparison_format", condition=condition)
            return False

        left_str = parts[0].strip()
        right_str = parts[1].strip()

        # Resolve variables in both sides
        left = self._resolve_value(left_str)
        right = self._resolve_value(right_str)

        # Perform comparison with proper type handling
        try:
            # Equality operators work on all types
            if operator == "==":
                return left == right
            elif operator == "!=":
                return left != right

            # Ordering operators require comparable types
            # Dict/list comparisons don't make sense, will raise TypeError
            elif operator == ">":
                return self._safe_compare(left, right, lambda lhs, rhs: lhs > rhs)
            elif operator == "<":
                return self._safe_compare(left, right, lambda lhs, rhs: lhs < rhs)
            elif operator == ">=":
                return self._safe_compare(left, right, lambda lhs, rhs: lhs >= rhs)
            elif operator == "<=":
                return self._safe_compare(left, right, lambda lhs, rhs: lhs <= rhs)
            else:
                return False
        except TypeError as e:
            logger.warning(
                "comparison_type_error",
                left=left,
                right=right,
                operator=operator,
                error=str(e),
            )
            return False

    def _safe_compare(
        self,
        left: ComparableValue | dict[str, Any] | list[Any],
        right: ComparableValue | dict[str, Any] | list[Any],
        comparison: Any,  # Callable but Any to avoid more complex typing
    ) -> bool:
        """Safely perform comparison, handling non-comparable types.

        Args:
            left: Left operand
            right: Right operand
            comparison: Comparison function (e.g., lambda l, r: l > r)

        Returns:
            Result of comparison

        Raises:
            TypeError: If types cannot be compared
        """
        # Dict and list types cannot be ordered
        if isinstance(left, (dict, list)) or isinstance(right, (dict, list)):
            raise TypeError(f"Cannot compare {type(left).__name__} with {type(right).__name__}")

        # For comparable values, perform the comparison
        return bool(comparison(left, right))

    def _evaluate_exists(self, condition: str) -> bool:
        """Evaluate an 'exists' condition.

        Args:
            condition: Condition string like "{{step1.field}} exists"

        Returns:
            True if the field exists, False otherwise
        """
        # Extract variable reference
        var_part = condition.replace(" exists", "").strip()

        try:
            # Try to resolve the variable
            self.resolver.resolve(var_part)
            return True
        except ValueError:
            # Variable doesn't exist
            return False

    def _evaluate_empty(self, condition: str) -> bool:
        """Evaluate an 'empty' or '!empty' condition.

        Args:
            condition: Condition string like "{{step1.items}} empty" or "{{step1.items}} !empty"

        Returns:
            True if condition is met, False otherwise
        """
        is_negated = "!empty" in condition
        var_part = condition.replace(" !empty", "").replace(" empty", "").strip()

        try:
            value = self._resolve_value(var_part)

            # Check if empty
            if isinstance(value, (list, dict, str)):
                is_empty = len(value) == 0
            else:
                is_empty = value is None

            return not is_empty if is_negated else is_empty

        except ValueError:
            # Variable doesn't exist, treat as empty
            return False if is_negated else True

    def _evaluate_boolean(self, condition: str) -> bool:
        """Evaluate a boolean condition.

        Args:
            condition: Condition string like "{{step1.success}}"

        Returns:
            Boolean value of the condition
        """
        value = self._resolve_value(condition)

        # Convert to boolean
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "yes", "1", "success")
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, (list, dict)):
            return len(value) > 0

        return bool(value)

    def _resolve_value(self, value_str: str) -> ComparableValue | dict[str, Any] | list[Any]:
        """Resolve a value string to its actual value.

        Args:
            value_str: String that may contain variables or literals

        Returns:
            Resolved value (primitives for comparisons, or dict/list for other checks)

        """
        value_str = value_str.strip()

        # Check if it's a variable reference
        if self.resolver.has_variables(value_str):
            return self.resolver.resolve(value_str)

        # Check if it's a quoted string literal
        if (value_str.startswith('"') and value_str.endswith('"')) or (
            value_str.startswith("'") and value_str.endswith("'")
        ):
            return value_str[1:-1]

        # Try to parse as number
        try:
            if "." in value_str:
                return float(value_str)
            return int(value_str)
        except ValueError:
            pass

        # Try to parse as boolean
        if value_str.lower() in ("true", "false"):
            return value_str.lower() == "true"

        # Return as string
        return value_str
