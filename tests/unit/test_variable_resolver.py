"""Unit tests for variable resolver."""

import pytest

from crawler.services.step_execution_context import StepExecutionContext, StepResult
from crawler.services.variable_resolver import VariableResolver


class TestVariableResolver:
    """Test suite for VariableResolver."""

    def test_resolve_simple_variable(self):
        """Test resolving a simple context variable."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        context.set_variable("api_key", "secret123")

        resolver = VariableResolver(context)
        result = resolver.resolve("https://api.example.com?key={{api_key}}")

        assert result == "https://api.example.com?key=secret123"

    def test_resolve_step_output_field(self):
        """Test resolving a field from step output."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        # Add step result with extracted data
        step_result = StepResult(
            step_name="fetch_list",
            extracted_data={"detail_url": "https://example.com/detail/123"},
        )
        context.add_result(step_result)

        resolver = VariableResolver(context)
        result = resolver.resolve("{{fetch_list.detail_url}}")

        assert result == "https://example.com/detail/123"

    def test_resolve_nested_field_access(self):
        """Test resolving nested fields from step output."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        # Add step result with nested data
        step_result = StepResult(
            step_name="api_call",
            extracted_data={"user": {"profile": {"name": "John Doe", "email": "john@example.com"}}},
        )
        context.add_result(step_result)

        resolver = VariableResolver(context)
        result = resolver.resolve("{{api_call.user.profile.name}}")

        assert result == "John Doe"

    def test_resolve_array_index(self):
        """Test resolving array element by index."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        # Add step result with array
        step_result = StepResult(
            step_name="fetch_items",
            extracted_data={"urls": ["http://example.com/1", "http://example.com/2"]},
        )
        context.add_result(step_result)

        resolver = VariableResolver(context)
        result = resolver.resolve("{{fetch_items.urls.0}}")

        assert result == "http://example.com/1"

    def test_resolve_multiple_variables(self):
        """Test resolving multiple variables in one template."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        context.set_variable("domain", "example.com")
        context.set_variable("protocol", "https")

        resolver = VariableResolver(context)
        result = resolver.resolve("{{protocol}}://{{domain}}/api/v1")

        assert result == "https://example.com/api/v1"

    def test_resolve_dict(self):
        """Test resolving variables in a dictionary."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        context.set_variable("api_key", "secret123")
        context.set_variable("user_id", "user456")

        resolver = VariableResolver(context)
        data = {
            "url": "https://api.example.com/users/{{user_id}}",
            "headers": {"Authorization": "Bearer {{api_key}}"},
        }

        result = resolver.resolve_dict(data)

        assert result["url"] == "https://api.example.com/users/user456"
        assert result["headers"]["Authorization"] == "Bearer secret123"

    def test_resolve_list(self):
        """Test resolving variables in a list."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        context.set_variable("base", "https://example.com")

        resolver = VariableResolver(context)
        data = ["{{base}}/page1", "{{base}}/page2", "{{base}}/page3"]

        result = resolver.resolve_list(data)

        assert result == [
            "https://example.com/page1",
            "https://example.com/page2",
            "https://example.com/page3",
        ]

    def test_error_variable_not_found(self):
        """Test error when variable is not found."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        resolver = VariableResolver(context)

        with pytest.raises(ValueError, match="Variable 'missing' not found"):
            resolver.resolve("{{missing}}")

    def test_error_step_not_executed(self):
        """Test error when referencing step that hasn't executed."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        resolver = VariableResolver(context)

        with pytest.raises(ValueError, match="has not been executed yet"):
            resolver.resolve("{{nonexistent_step.field}}")

    def test_error_field_not_found(self):
        """Test error when field doesn't exist in step output."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        step_result = StepResult(
            step_name="step1",
            extracted_data={"field1": "value1"},
        )
        context.add_result(step_result)

        resolver = VariableResolver(context)

        with pytest.raises(ValueError, match="Field 'missing_field' not found"):
            resolver.resolve("{{step1.missing_field}}")

    def test_error_invalid_array_index(self):
        """Test error with invalid array index."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        step_result = StepResult(
            step_name="step1",
            extracted_data={"items": ["a", "b"]},
        )
        context.add_result(step_result)

        resolver = VariableResolver(context)

        with pytest.raises(ValueError, match="Invalid array index"):
            resolver.resolve("{{step1.items.invalid}}")

    def test_has_variables(self):
        """Test checking if template contains variables."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        resolver = VariableResolver(context)

        assert resolver.has_variables("{{var}}") is True
        assert resolver.has_variables("no variables here") is False
        assert resolver.has_variables("partial {{var}} match") is True

    def test_extract_variable_names(self):
        """Test extracting variable names from template."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        resolver = VariableResolver(context)

        names = resolver.extract_variable_names("{{var1}} and {{var2}} and {{var3}}")

        assert names == ["var1", "var2", "var3"]

    def test_resolve_non_string_returns_original(self):
        """Test that resolving non-string values returns original."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        resolver = VariableResolver(context)

        assert resolver.resolve(123) == 123
        assert resolver.resolve(None) is None
        assert resolver.resolve(True) is True
