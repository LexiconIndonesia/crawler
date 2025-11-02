"""Variable substitution system supporting multiple variable sources.

This module provides a comprehensive variable substitution system that can resolve
variables from multiple sources:
- ${variables.key} - Job submission variables
- ${ENV.KEY} - Environment variables (from database)
- ${input.field} - Output from previous crawl step
- ${pagination.current_page} - Auto-incremented page counter
- ${metadata.field} - Job metadata fields

The system supports type conversion, error handling, and recursive substitution
with circular reference detection.
"""

import json
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any, TypeVar

from crawler.core.logging import get_logger

logger = get_logger(__name__)

# Type variable for type conversion
T = TypeVar("T")

# Regular expression pattern for variable substitution
# Matches ${source.path} where source can be any word
VARIABLE_PATTERN = re.compile(r"\$\{(?P<source>\w+)(?:\.(?P<path>[^}]*))?\}")

# Escape pattern for literal ${...}
ESCAPE_PATTERN = re.compile(r"\\\$\{([^}]+)\}")


class VariableError(Exception):
    """Base exception for variable substitution errors."""

    def __init__(self, message: str, variable: str, source: str | None = None):
        self.variable = variable
        self.source = source
        super().__init__(message)


class VariableNotFoundError(VariableError):
    """Raised when a variable cannot be found."""

    def __init__(self, variable: str, source: str, path: str):
        message = f"Variable '{variable}' not found in {source}: {path}"
        super().__init__(message, variable, source)


class CircularReferenceError(VariableError):
    """Raised when circular variable reference is detected."""

    def __init__(self, variable: str, chain: list[str]):
        chain_str = " -> ".join(chain)
        message = f"Circular reference detected for variable '{variable}': {chain_str}"
        super().__init__(message, variable)


class TypeConversionError(VariableError):
    """Raised when type conversion fails."""

    def __init__(self, variable: str, value: Any, target_type: type, error: str):
        message = (
            f"Cannot convert variable '{variable}' value '{value}' to "
            f"{target_type.__name__}: {error}"
        )
        super().__init__(message, variable)


@dataclass
class VariableContext:
    """Context for variable resolution."""

    # Job submission variables
    job_variables: dict[str, Any] = field(default_factory=dict)

    # Environment variables (from database or os.environ)
    environment: dict[str, Any] = field(default_factory=dict)

    # Input from previous step
    step_input: dict[str, Any] = field(default_factory=dict)

    # Pagination state
    pagination_state: dict[str, Any] = field(default_factory=dict)

    # Job metadata
    metadata: dict[str, Any] = field(default_factory=dict)

    # Configuration
    strict_mode: bool = True  # If True, missing variables raise errors
    max_recursion_depth: int = 10
    allow_env_fallback: bool = True  # Allow fallback to os.environ

    def merge(self, other: "VariableContext") -> "VariableContext":
        """Merge with another context, other takes precedence."""
        return VariableContext(
            job_variables={**self.job_variables, **other.job_variables},
            environment={**self.environment, **other.environment},
            step_input={**self.step_input, **other.step_input},
            pagination_state={**self.pagination_state, **other.pagination_state},
            metadata={**self.metadata, **other.metadata},
            strict_mode=other.strict_mode,
            max_recursion_depth=min(self.max_recursion_depth, other.max_recursion_depth),
            allow_env_fallback=other.allow_env_fallback,
        )


class VariableProvider(ABC):
    """Abstract base class for variable providers."""

    @abstractmethod
    def get(self, path: str, context: VariableContext) -> Any:
        """Get a variable value by path."""
        pass

    @abstractmethod
    def source_name(self) -> str:
        """Get the source name for error reporting."""
        pass

    def list_available(self, context: VariableContext) -> list[str]:
        """List all available variables from this provider."""
        return []


class DictNavigationMixin:
    """Mixin providing dictionary navigation utilities for variable providers.

    This mixin provides shared implementations of _get_nested and _flatten_keys
    methods that are commonly used by providers that work with nested dictionaries.

    The _get_nested method can be overridden by subclasses to customize error
    handling behavior (e.g., returning None instead of raising KeyError).
    """

    def _get_nested(self, data: dict[str, Any], path: str) -> Any:
        """Get nested value from dictionary using dot notation.

        Args:
            data: Dictionary to navigate
            path: Dot-separated path (e.g., "user.profile.email")

        Returns:
            Value at the specified path

        Raises:
            KeyError: If path is empty or any key in the path is not found
        """
        if not path:
            raise KeyError("Empty path")
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                raise KeyError(f"Key '{key}' not found in path '{path}'")

        return current

    def _flatten_keys(self, data: dict[str, Any], prefix: str = "") -> list[str]:
        """Flatten nested dictionary keys to dot notation.

        Args:
            data: Dictionary to flatten
            prefix: Current key prefix for recursion

        Returns:
            List of flattened key paths (e.g., ["user.name", "user.email"])

        Example:
            >>> mixin._flatten_keys({"user": {"name": "John", "email": "john@example.com"}})
            ["user.name", "user.email"]
        """
        keys = []
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, dict):
                keys.extend(self._flatten_keys(value, full_key))
            else:
                keys.append(full_key)
        return keys


class JobVariablesProvider(DictNavigationMixin, VariableProvider):
    """Provider for job submission variables (${variables.*}).

    Inherits dictionary navigation utilities from DictNavigationMixin.
    """

    def get(self, path: str, context: VariableContext) -> Any:
        """Get job variable by path."""
        if not path:
            raise KeyError("Empty path")
        return self._get_nested(context.job_variables, path)

    def source_name(self) -> str:
        return "variables"

    def list_available(self, context: VariableContext) -> list[str]:
        return self._flatten_keys(context.job_variables)


class EnvironmentProvider(DictNavigationMixin, VariableProvider):
    """Provider for environment variables (${ENV.*}).

    Inherits from DictNavigationMixin but overrides _get_nested to return None
    instead of raising KeyError, allowing fallback to os.environ.
    """

    def get(self, path: str, context: VariableContext) -> Any:
        """Get environment variable by path."""
        # Try database environment first
        value = self._get_nested(context.environment, path)

        # Fallback to os.environ if allowed
        if value is None and context.allow_env_fallback:
            value = os.getenv(path)

        if value is None:
            raise KeyError(f"Environment variable '{path}' not found")

        return value

    def source_name(self) -> str:
        return "ENV"

    def list_available(self, context: VariableContext) -> list[str]:
        keys = list(context.environment.keys())
        if context.allow_env_fallback:
            keys.extend(os.environ.keys())
        return list(set(keys))  # Remove duplicates

    def _get_nested(self, data: dict[str, Any], path: str) -> Any:
        """Get nested value from environment dictionary.

        Overrides parent to return None instead of raising KeyError,
        allowing fallback to os.environ.

        Args:
            data: Dictionary to navigate
            path: Dot-separated path

        Returns:
            Value at path or None if not found
        """
        keys = path.split(".")
        current = data

        for key in keys:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                return None

        return current


class InputProvider(DictNavigationMixin, VariableProvider):
    """Provider for previous step output (${input.*}).

    Inherits dictionary navigation utilities from DictNavigationMixin.
    """

    def get(self, path: str, context: VariableContext) -> Any:
        """Get input variable by path."""
        return self._get_nested(context.step_input, path)

    def source_name(self) -> str:
        return "input"

    def list_available(self, context: VariableContext) -> list[str]:
        return self._flatten_keys(context.step_input)


class PaginationProvider(VariableProvider):
    """Provider for pagination variables (${pagination.*})."""

    # Built-in pagination variables
    BUILTIN_VARS = {
        "current_page": 1,
        "page_size": 10,
        "total_pages": 0,
        "total_items": 0,
        "offset": 0,
    }

    def get(self, path: str, context: VariableContext) -> Any:
        """Get pagination variable by path."""
        # Check context first
        if path in context.pagination_state:
            return context.pagination_state[path]

        # Check built-in variables
        if path in self.BUILTIN_VARS:
            return self.BUILTIN_VARS[path]

        raise KeyError(f"Pagination variable '{path}' not found")

    def source_name(self) -> str:
        return "pagination"

    def list_available(self, context: VariableContext) -> list[str]:
        builtin = list(self.BUILTIN_VARS.keys())
        contextual = list(context.pagination_state.keys())
        return builtin + contextual


class MetadataProvider(DictNavigationMixin, VariableProvider):
    """Provider for job metadata (${metadata.*}).

    Inherits dictionary navigation utilities from DictNavigationMixin.
    """

    def get(self, path: str, context: VariableContext) -> Any:
        """Get metadata variable by path."""
        return self._get_nested(context.metadata, path)

    def source_name(self) -> str:
        return "metadata"

    def list_available(self, context: VariableContext) -> list[str]:
        return self._flatten_keys(context.metadata)


class VariableResolver:
    """Main variable resolver with support for multiple sources."""

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        self._providers = {
            "variables": JobVariablesProvider(),
            "ENV": EnvironmentProvider(),
            "input": InputProvider(),
            "pagination": PaginationProvider(),
            "metadata": MetadataProvider(),
        }

    def substitute(
        self,
        text: str,
        context: VariableContext,
        *,
        convert_types: bool = True,
        recursion_depth: int = 0,
        _visited: set[str] | None = None,
    ) -> str:
        """Substitute variables in a string.

        Args:
            text: The text containing variable references
            context: Variable resolution context
            convert_types: Whether to attempt type conversion
            recursion_depth: Current recursion depth (internal)
            _visited: Set of visited variables for circular reference detection

        Returns:
            String with all variables substituted

        Raises:
            VariableNotFoundError: If a variable is not found (in strict mode)
            CircularReferenceError: If circular reference is detected
            TypeConversionError: If type conversion fails
        """
        if _visited is None:
            _visited = set()

        if recursion_depth > context.max_recursion_depth:
            raise VariableError(
                f"Maximum recursion depth ({context.max_recursion_depth}) exceeded", "unknown"
            )

        # First, handle escaped variables by replacing them with placeholders
        escaped_vars: dict[str, str] = {}
        placeholder_pattern = "__ESCAPED_VAR_%d__"

        def replace_escaped(match: re.Match) -> str:
            escaped_content = match.group(1)
            placeholder = placeholder_pattern % len(escaped_vars)
            escaped_vars[placeholder] = f"${{{escaped_content}}}"
            return placeholder

        text = ESCAPE_PATTERN.sub(replace_escaped, text)

        # Find all variable references
        def replace_match(match: re.Match) -> str:
            source = match.group("source")
            path = match.group("path") or ""
            full_var = match.group(0)

            # Check for circular reference
            if full_var in _visited:
                raise CircularReferenceError(full_var, list(_visited))

            # Get the provider
            provider = self._providers.get(source)
            if not provider:
                if context.strict_mode:
                    raise VariableNotFoundError(full_var, source, path)
                logger.warning(
                    "Unknown variable source", source=source, path=path, variable=full_var
                )
                return str(full_var)

            # Resolve the variable
            try:
                with self._track_recursion(_visited, full_var):
                    value = provider.get(path, context)

                    # If the value is a string, recursively substitute
                    if isinstance(value, str):
                        value = self.substitute(
                            value,
                            context,
                            convert_types=convert_types,
                            recursion_depth=recursion_depth + 1,
                            _visited=_visited.copy(),
                        )

                    # Convert to string for substitution
                    return str(value)

            except KeyError as e:
                if context.strict_mode:
                    raise VariableNotFoundError(full_var, source, str(e))
                logger.warning(
                    "Variable not found", source=source, path=path, error=str(e), variable=full_var
                )
                return str(full_var)
            except CircularReferenceError:
                # Re-raise circular reference errors as-is
                raise
            except Exception as e:
                logger.error(
                    "Error resolving variable",
                    source=source,
                    path=path,
                    error=str(e),
                    variable=full_var,
                )
                if context.strict_mode:
                    raise VariableError(f"Error resolving variable: {e}", full_var, source)
                return str(full_var)

        # Perform substitution
        result = VARIABLE_PATTERN.sub(replace_match, text)

        # Restore escaped variables
        for placeholder, original in escaped_vars.items():
            result = result.replace(placeholder, original)

        return result

    @contextmanager
    def _track_recursion(self, visited: set[str], variable: str) -> Generator[None, None, None]:
        """Context manager for tracking variable recursion."""
        visited.add(variable)
        try:
            yield
        finally:
            visited.discard(variable)

    def substitute_in_dict(
        self,
        data: dict[str, Any],
        context: VariableContext,
        *,
        convert_types: bool = True,
        recurse: bool = True,
        recursion_depth: int = 0,
    ) -> dict[str, Any]:
        """Substitute variables in all string values of a dictionary.

        Args:
            data: Dictionary containing string values with variables
            context: Variable resolution context
            convert_types: Whether to attempt type conversion
            recurse: Whether to recursively process nested dictionaries
            recursion_depth: Current recursion depth

        Returns:
            Dictionary with all string values substituted
        """
        if recursion_depth > context.max_recursion_depth:
            raise VariableError(
                f"Maximum recursion depth ({context.max_recursion_depth}) exceeded",
                "dict_substitution",
            )

        result = {}

        for key, value in data.items():
            if isinstance(value, str):
                # Substitute variables in string
                substituted = self.substitute(value, context, convert_types=convert_types)

                # Attempt type conversion
                if convert_types:
                    value = self._convert_type(substituted)
                else:
                    value = substituted

            elif isinstance(value, dict) and recurse:
                # Recursively process nested dictionaries
                value = self.substitute_in_dict(
                    value,
                    context,
                    convert_types=convert_types,
                    recurse=recurse,
                    recursion_depth=recursion_depth + 1,
                )

            elif isinstance(value, list) and recurse:
                # Process lists
                value = [
                    self.substitute_in_dict(
                        item,
                        context,
                        convert_types=convert_types,
                        recurse=recurse,
                        recursion_depth=recursion_depth + 1,
                    )
                    if isinstance(item, dict)
                    else self.substitute(item, context, convert_types=convert_types)
                    if isinstance(item, str)
                    else item
                    for item in value
                ]

            result[key] = value

        return result

    def substitute_in_list(
        self,
        data: list[Any],
        context: VariableContext,
        *,
        convert_types: bool = True,
        recurse: bool = True,
    ) -> list[Any]:
        """Substitute variables in all string values of a list."""
        result = []

        for item in data:
            if isinstance(item, str):
                substituted = self.substitute(item, context, convert_types=convert_types)
                if convert_types:
                    item = self._convert_type(substituted)
                else:
                    item = substituted

            elif isinstance(item, dict) and recurse:
                item = self.substitute_in_dict(item, context, convert_types=convert_types)

            elif isinstance(item, list) and recurse:
                item = self.substitute_in_list(item, context, convert_types=convert_types)

            result.append(item)

        return result

    def get_variable(
        self,
        variable_path: str,
        context: VariableContext,
        default: Any = None,
        *,
        convert_type: type[T] | None = None,
    ) -> Any:
        """Get a specific variable value.

        Args:
            variable_path: Full variable path (e.g., "variables.api_key")
            context: Variable resolution context
            default: Default value if variable not found
            convert_type: Optional type to convert the value to

        Returns:
            Variable value or default
        """
        # Parse the variable path
        if not variable_path.startswith("${"):
            # Direct value, no substitution needed
            return variable_path

        # Extract source and path from ${source.path}
        match = VARIABLE_PATTERN.match(variable_path)
        if not match:
            raise ValueError(f"Invalid variable path format: {variable_path}")

        source = match.group("source")
        path = match.group("path") or ""

        # Get the provider
        provider = self._providers.get(source)
        if not provider:
            if default is not None:
                return default
            raise VariableNotFoundError(variable_path, source, path)

        # Get the value
        try:
            value = provider.get(path, context)

            # Recursively substitute if value is a string
            if isinstance(value, str):
                value = self.substitute(value, context)

            # Convert type if requested
            if convert_type and value is not None:
                value = self.convert_type(value, convert_type)

            return value

        except KeyError:
            if default is not None:
                return default
            raise VariableNotFoundError(variable_path, source, path)

    def list_available_variables(self, context: VariableContext) -> dict[str, list[str]]:
        """List all available variables by source."""
        result = {}
        for source, provider in self._providers.items():
            result[source] = provider.list_available(context)
        return result

    @staticmethod
    def convert_type(value: Any, target_type: type) -> Any:
        """Convert a value to the specified type.

        Args:
            value: Value to convert
            target_type: Target type (int, float, bool, str, list, dict)

        Returns:
            Converted value

        Raises:
            TypeConversionError: If conversion fails
        """
        if value is None:
            return None

        # Already the correct type
        if isinstance(value, target_type):
            return value

        # Convert to string first if needed
        if not isinstance(value, str):
            value = str(value)

        try:
            if target_type is bool:
                # Handle boolean conversion
                if value.lower() in ("true", "1", "yes", "on", "y"):
                    return True
                elif value.lower() in ("false", "0", "no", "off", "n"):
                    return False
                else:
                    raise ValueError(f"Cannot convert '{value}' to boolean")

            elif target_type is int:
                # Handle integer conversion
                return int(float(value))  # Handles "1.0" -> 1

            elif target_type is float:
                return float(value)

            elif target_type is str:
                return str(value)

            elif target_type is list:
                # Handle list conversion (comma-separated)
                if not value:
                    return []
                return [item.strip() for item in value.split(",")]

            elif target_type is dict:
                # Handle JSON-like string conversion
                return json.loads(value)

            else:
                raise TypeConversionError(
                    "unknown", value, target_type, f"Unsupported target type: {target_type}"
                )

        except (ValueError, json.JSONDecodeError) as e:
            raise TypeConversionError("unknown", value, target_type, str(e))

    def _convert_type(self, value: str) -> Any:
        """Attempt to automatically convert string to appropriate type."""
        # Try boolean
        if value.lower() in ("true", "false"):
            return value.lower() == "true"

        # Try integer
        try:
            if "." not in value and "e" not in value.lower():
                return int(value)
        except ValueError:
            pass

        # Try float
        try:
            return float(value)
        except ValueError:
            pass

        # Try JSON (list or dict)
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            pass

        # Return as string
        return value

    def validate_variables(self, text: str, context: VariableContext) -> list[VariableError]:
        """Validate that all variables in text can be resolved.

        Args:
            text: Text containing variable references
            context: Variable resolution context

        Returns:
            List of validation errors (empty if all valid)
        """
        errors: list[VariableError] = []

        # Find all variables and validate them
        for match in VARIABLE_PATTERN.finditer(text):
            source = match.group("source")
            path = match.group("path") or ""
            full_var = match.group(0)

            # Get the provider
            provider = self._providers.get(source)
            if not provider:
                errors.append(VariableNotFoundError(full_var, source, path))
                continue

            # Try to get the value
            try:
                provider.get(path, context)
            except KeyError:
                errors.append(VariableNotFoundError(full_var, source, path))
            except Exception as e:
                errors.append(VariableError(f"Error validating variable: {e}", full_var, source))

        return errors


# Global instance for convenience
default_resolver = VariableResolver()


# Convenience functions
def substitute(text: str, context: VariableContext, **kwargs: Any) -> str:
    """Substitute variables in a string using the default resolver."""
    return default_resolver.substitute(text, context, **kwargs)


def substitute_dict(
    data: dict[str, Any], context: VariableContext, **kwargs: Any
) -> dict[str, Any]:
    """Substitute variables in a dictionary using the default resolver."""
    return default_resolver.substitute_in_dict(data, context, **kwargs)


def get_variable(
    variable_path: str, context: VariableContext, default: Any = None, **kwargs: Any
) -> Any:
    """Get a variable value using the default resolver."""
    return default_resolver.get_variable(variable_path, context, default, **kwargs)


def validate_variables(text: str, context: VariableContext) -> list[VariableError]:
    """Validate variables in text using the default resolver."""
    return default_resolver.validate_variables(text, context)
