"""Unit tests for variable substitution system."""

import os

import pytest

from crawler.utils.variable_substitution import (
    CircularReferenceError,
    EnvironmentProvider,
    InputProvider,
    JobVariablesProvider,
    MetadataProvider,
    PaginationProvider,
    TypeConversionError,
    VariableContext,
    VariableError,
    VariableNotFoundError,
    VariableResolver,
    get_variable,
    substitute,
    substitute_dict,
    validate_variables,
)


class TestVariableContext:
    """Test VariableContext class."""

    def test_context_creation(self):
        """Test creating a variable context."""
        context = VariableContext(
            job_variables={"api_key": "secret"},
            environment={"DB_HOST": "localhost"},
            strict_mode=False,
        )

        assert context.job_variables == {"api_key": "secret"}
        assert context.environment == {"DB_HOST": "localhost"}
        assert context.strict_mode is False
        assert context.max_recursion_depth == 10

    def test_context_merge(self):
        """Test merging two contexts."""
        context1 = VariableContext(
            job_variables={"key1": "value1"},
            environment={"ENV1": "val1"},
            strict_mode=True,
        )

        context2 = VariableContext(
            job_variables={"key2": "value2"},
            environment={"ENV2": "val2"},
            strict_mode=False,
        )

        merged = context1.merge(context2)

        assert merged.job_variables == {"key1": "value1", "key2": "value2"}
        assert merged.environment == {"ENV1": "val1", "ENV2": "val2"}
        assert merged.strict_mode is False  # context2 takes precedence

    def test_context_merge_empty(self):
        """Test merging with empty context."""
        context1 = VariableContext(job_variables={"key": "value"})
        context2 = VariableContext()

        merged = context1.merge(context2)
        assert merged.job_variables == {"key": "value"}


class TestJobVariablesProvider:
    """Test JobVariablesProvider."""

    def test_get_simple_variable(self):
        """Test getting a simple variable."""
        provider = JobVariablesProvider()
        context = VariableContext(job_variables={"api_key": "secret123"})

        value = provider.get("api_key", context)
        assert value == "secret123"

    def test_get_nested_variable(self):
        """Test getting a nested variable."""
        provider = JobVariablesProvider()
        context = VariableContext(
            job_variables={
                "auth": {"bearer": {"token": "abc123"}, "type": "Bearer"},
                "endpoints": {"users": "/api/users", "posts": "/api/posts"},
            }
        )

        assert provider.get("auth.bearer.token", context) == "abc123"
        assert provider.get("auth.type", context) == "Bearer"
        assert provider.get("endpoints.users", context) == "/api/users"

    def test_get_missing_variable(self):
        """Test getting a missing variable raises KeyError."""
        provider = JobVariablesProvider()
        context = VariableContext(job_variables={"existing": "value"})

        with pytest.raises(KeyError, match="Key 'missing' not found"):
            provider.get("missing", context)

        with pytest.raises(KeyError, match="Key 'missing' not found"):
            provider.get("missing.deep.key", context)

    def test_get_missing_nested_key(self):
        """Test getting missing nested key."""
        provider = JobVariablesProvider()
        context = VariableContext(job_variables={"existing": {"nested": "value"}})

        with pytest.raises(KeyError, match="Key 'missing' not found"):
            provider.get("existing.missing", context)

    def test_list_available(self):
        """Test listing available variables."""
        provider = JobVariablesProvider()
        context = VariableContext(
            job_variables={
                "api_key": "secret",
                "auth": {"token": "abc", "type": "Bearer"},
                "endpoints": {"users": "/api/users"},
            }
        )

        available = provider.list_available(context)
        assert "api_key" in available
        assert "auth.token" in available
        assert "auth.type" in available
        assert "endpoints.users" in available
        assert len(available) == 4


class TestEnvironmentProvider:
    """Test EnvironmentProvider."""

    def test_get_env_variable(self):
        """Test getting environment variable from context."""
        provider = EnvironmentProvider()
        context = VariableContext(environment={"DB_HOST": "localhost", "PORT": "5432"})

        assert provider.get("DB_HOST", context) == "localhost"
        assert provider.get("PORT", context) == "5432"

    def test_get_nested_env_variable(self):
        """Test getting nested environment variable."""
        provider = EnvironmentProvider()
        context = VariableContext(
            environment={
                "database": {"host": "localhost", "port": "5432"},
                "redis": {"url": "redis://localhost:6379"},
            }
        )

        assert provider.get("database.host", context) == "localhost"
        assert provider.get("database.port", context) == "5432"
        assert provider.get("redis.url", context) == "redis://localhost:6379"

    def test_fallback_to_os_environ(self):
        """Test fallback to os.environ."""
        provider = EnvironmentProvider()
        context = VariableContext(allow_env_fallback=True)

        # Set a temporary environment variable
        os.environ["TEST_VAR"] = "test_value"
        try:
            value = provider.get("TEST_VAR", context)
            assert value == "test_value"
        finally:
            del os.environ["TEST_VAR"]

    def test_no_fallback_to_os_environ(self):
        """Test no fallback when disabled."""
        provider = EnvironmentProvider()
        context = VariableContext(allow_env_fallback=False)

        # Set a temporary environment variable
        os.environ["TEST_VAR"] = "test_value"
        try:
            with pytest.raises(KeyError):
                provider.get("TEST_VAR", context)
        finally:
            del os.environ["TEST_VAR"]

    def test_missing_variable(self):
        """Test missing environment variable."""
        provider = EnvironmentProvider()
        context = VariableContext(environment={}, allow_env_fallback=False)

        with pytest.raises(KeyError, match="Environment variable 'MISSING' not found"):
            provider.get("MISSING", context)


class TestInputProvider:
    """Test InputProvider."""

    def test_get_input_variable(self):
        """Test getting input variable."""
        provider = InputProvider()
        context = VariableContext(step_input={"user_id": "123", "result": "success"})

        assert provider.get("user_id", context) == "123"
        assert provider.get("result", context) == "success"

    def test_get_nested_input(self):
        """Test getting nested input variable."""
        provider = InputProvider()
        context = VariableContext(
            step_input={
                "user": {"id": "123", "name": "John"},
                "response": {"data": {"items": [1, 2, 3], "total": 3}},
            }
        )

        assert provider.get("user.id", context) == "123"
        assert provider.get("user.name", context) == "John"
        assert provider.get("response.data.items", context) == [1, 2, 3]
        assert provider.get("response.data.total", context) == 3

    def test_missing_input(self):
        """Test missing input variable."""
        provider = InputProvider()
        context = VariableContext(step_input={})

        with pytest.raises(KeyError, match="Key 'missing' not found"):
            provider.get("missing", context)


class TestPaginationProvider:
    """Test PaginationProvider."""

    def test_get_builtin_variable(self):
        """Test getting built-in pagination variable."""
        provider = PaginationProvider()
        context = VariableContext()

        assert provider.get("current_page", context) == 1
        assert provider.get("page_size", context) == 10
        assert provider.get("total_pages", context) == 0
        assert provider.get("total_items", context) == 0
        assert provider.get("offset", context) == 0

    def test_get_context_variable(self):
        """Test getting pagination variable from context."""
        provider = PaginationProvider()
        context = VariableContext(
            pagination_state={
                "current_page": 5,
                "cursor": "abc123",
                "has_next": True,
            }
        )

        # Context takes precedence over built-ins
        assert provider.get("current_page", context) == 5
        assert provider.get("cursor", context) == "abc123"
        assert provider.get("has_next", context) is True

        # Built-in still available if not in context
        assert provider.get("page_size", context) == 10

    def test_missing_variable(self):
        """Test missing pagination variable."""
        provider = PaginationProvider()
        context = VariableContext()

        with pytest.raises(KeyError, match="Pagination variable 'missing' not found"):
            provider.get("missing", context)

    def test_list_available(self):
        """Test listing available pagination variables."""
        provider = PaginationProvider()
        context = VariableContext(pagination_state={"custom_var": "value"})

        available = provider.list_available(context)
        assert "current_page" in available
        assert "page_size" in available
        assert "custom_var" in available
        assert len(available) >= 6  # At least 5 built-ins + 1 custom


class TestMetadataProvider:
    """Test MetadataProvider."""

    def test_get_metadata_variable(self):
        """Test getting metadata variable."""
        provider = MetadataProvider()
        context = VariableContext(
            metadata={"job_id": "123", "created_at": "2025-01-01", "tags": ["test"]}
        )

        assert provider.get("job_id", context) == "123"
        assert provider.get("created_at", context) == "2025-01-01"
        assert provider.get("tags", context) == ["test"]

    def test_get_nested_metadata(self):
        """Test getting nested metadata variable."""
        provider = MetadataProvider()
        context = VariableContext(
            metadata={
                "crawl": {"depth": 3, "pages": 10},
                "source": {"website": {"url": "https://example.com", "name": "Example"}},
            }
        )

        assert provider.get("crawl.depth", context) == 3
        assert provider.get("crawl.pages", context) == 10
        assert provider.get("source.website.url", context) == "https://example.com"
        assert provider.get("source.website.name", context) == "Example"

    def test_missing_metadata(self):
        """Test missing metadata variable."""
        provider = MetadataProvider()
        context = VariableContext(metadata={})

        with pytest.raises(KeyError, match="Key 'missing' not found"):
            provider.get("missing", context)


class TestVariableResolver:
    """Test VariableResolver class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.resolver = VariableResolver()
        self.context = VariableContext(
            job_variables={
                "api_key": "secret123",
                "base_url": "https://api.example.com",
                "auth": {"token": "abc123"},
            },
            environment={"ENV_VAR": "env_value"},
            step_input={"result": "success", "count": 42},
            pagination_state={"current_page": 3},
            metadata={"job_id": "job_123"},
        )

    def test_substitute_simple_variable(self):
        """Test substituting a simple variable."""
        text = "Bearer ${variables.api_key}"
        result = self.resolver.substitute(text, self.context)
        assert result == "Bearer secret123"

    def test_substitute_multiple_variables(self):
        """Test substituting multiple variables in one string."""
        text = "${variables.base_url}/v1/${variables.api_key}"
        result = self.resolver.substitute(text, self.context)
        assert result == "https://api.example.com/v1/secret123"

    def test_substitute_different_sources(self):
        """Test substituting variables from different sources."""
        text = "Job: ${metadata.job_id}, Page: ${pagination.current_page}, Env: ${ENV.ENV_VAR}"
        result = self.resolver.substitute(text, self.context)
        assert result == "Job: job_123, Page: 3, Env: env_value"

    def test_substitute_nested_variables(self):
        """Test substituting nested variables."""
        text = "Token: ${variables.auth.token}"
        result = self.resolver.substitute(text, self.context)
        assert result == "Token: abc123"

    def test_substitute_no_variables(self):
        """Test text with no variables."""
        text = "Just a plain string"
        result = self.resolver.substitute(text, self.context)
        assert result == text

    def test_substitute_missing_variable_strict(self):
        """Test missing variable in strict mode."""
        text = "Missing: ${variables.missing}"
        with pytest.raises(VariableNotFoundError):
            self.resolver.substitute(text, self.context)

    def test_substitute_missing_variable_non_strict(self):
        """Test missing variable in non-strict mode."""
        self.resolver.strict_mode = False
        self.context.strict_mode = False
        text = "Missing: ${variables.missing}"
        result = self.resolver.substitute(text, self.context)
        assert result == "Missing: ${variables.missing}"

    def test_substitute_unknown_source(self):
        """Test unknown variable source."""
        text = "Unknown: ${unknown.source}"
        with pytest.raises(VariableNotFoundError):
            self.resolver.substitute(text, self.context)

    def test_substitute_escaped_variable(self):
        """Test escaped variable."""
        text = r"Literal: \${variables.api_key}, Substituted: ${variables.api_key}"
        result = self.resolver.substitute(text, self.context)
        assert result == "Literal: ${variables.api_key}, Substituted: secret123"

    def test_substitute_recursive(self):
        """Test recursive variable substitution."""
        context = VariableContext(
            job_variables={
                "base_url": "https://example.com",
                "endpoint": "${variables.base_url}/api",
                "full_url": "${variables.endpoint}/v1",
            }
        )

        result = self.resolver.substitute("${variables.full_url}", context)
        assert result == "https://example.com/api/v1"

    def test_circular_reference_detection(self):
        """Test circular reference detection."""
        context = VariableContext(
            job_variables={"var1": "${variables.var2}", "var2": "${variables.var1}"}
        )

        with pytest.raises(CircularReferenceError):
            self.resolver.substitute("${variables.var1}", context)

    def test_max_recursion_depth(self):
        """Test maximum recursion depth."""
        # Create a chain of variables longer than max depth
        chain = {}
        for i in range(15):  # More than default max_depth of 10
            chain[f"var{i}"] = f"${{variables.var{i + 1}}}"
        chain["var15"] = "final"

        context = VariableContext(job_variables=chain)

        with pytest.raises(VariableError, match="Maximum recursion depth"):
            self.resolver.substitute("${variables.var0}", context)

    def test_substitute_in_dict(self):
        """Test substituting variables in dictionary."""
        data = {
            "url": "${variables.base_url}/api",
            "headers": {
                "Authorization": "Bearer ${variables.api_key}",
                "X-Job-ID": "${metadata.job_id}",
            },
            "params": {
                "page": "${pagination.current_page}",
                "env": "${ENV.ENV_VAR}",
            },
            "static": "no_variables",
        }

        result = self.resolver.substitute_in_dict(data, self.context, convert_types=False)

        expected = {
            "url": "https://api.example.com/api",
            "headers": {
                "Authorization": "Bearer secret123",
                "X-Job-ID": "job_123",
            },
            "params": {"page": "3", "env": "env_value"},
            "static": "no_variables",
        }

        assert result == expected

    def test_substitute_in_dict_nested(self):
        """Test substituting variables in nested dictionary."""
        data = {
            "level1": {
                "level2": {
                    "value": "${variables.api_key}",
                    "nested": {"deep": "${metadata.job_id}"},
                }
            },
        }

        result = self.resolver.substitute_in_dict(data, self.context)
        assert result["level1"]["level2"]["value"] == "secret123"
        assert result["level1"]["level2"]["nested"]["deep"] == "job_123"

    def test_substitute_in_dict_with_lists(self):
        """Test substituting variables in dictionary with lists."""
        data = {
            "urls": [
                "${variables.base_url}/users",
                "${variables.base_url}/posts",
            ],
            "config": {
                "auth": ["Bearer", "${variables.api_key}"],
                "metadata": {"job": "${metadata.job_id}"},
            },
        }

        result = self.resolver.substitute_in_dict(data, self.context, convert_types=False)

        assert result["urls"] == [
            "https://api.example.com/users",
            "https://api.example.com/posts",
        ]
        assert result["config"]["auth"] == ["Bearer", "secret123"]
        assert result["config"]["metadata"]["job"] == "job_123"

    def test_get_variable(self):
        """Test getting a specific variable."""
        value = self.resolver.get_variable("${variables.api_key}", self.context)
        assert value == "secret123"

        # With type conversion
        value = self.resolver.get_variable("${input.count}", self.context, convert_type=int)
        assert value == 42
        assert isinstance(value, int)

    def test_get_variable_with_default(self):
        """Test getting variable with default value."""
        value = self.resolver.get_variable(
            "${variables.missing}", self.context, default="default_value"
        )
        assert value == "default_value"

    def test_get_variable_direct_value(self):
        """Test getting variable without ${} syntax returns direct value."""
        value = self.resolver.get_variable("direct_value", self.context)
        assert value == "direct_value"

    def test_list_available_variables(self):
        """Test listing all available variables."""
        available = self.resolver.list_available_variables(self.context)

        assert "variables" in available
        assert "ENV" in available
        assert "input" in available
        assert "pagination" in available
        assert "metadata" in available

        assert "api_key" in available["variables"]
        assert "ENV_VAR" in available["ENV"]
        assert "result" in available["input"]
        assert "current_page" in available["pagination"]
        assert "job_id" in available["metadata"]

    def test_convert_type(self):
        """Test type conversion."""
        # Boolean conversion
        assert self.resolver.convert_type("true", bool) is True
        assert self.resolver.convert_type("false", bool) is False
        assert self.resolver.convert_type("1", bool) is True
        assert self.resolver.convert_type("0", bool) is False
        assert self.resolver.convert_type("yes", bool) is True
        assert self.resolver.convert_type("no", bool) is False

        # Integer conversion
        assert self.resolver.convert_type("42", int) == 42
        assert self.resolver.convert_type("3.0", int) == 3
        assert self.resolver.convert_type("-10", int) == -10

        # Float conversion
        assert self.resolver.convert_type("3.14", float) == 3.14
        assert self.resolver.convert_type("2", float) == 2.0

        # String conversion
        assert self.resolver.convert_type(123, str) == "123"

        # List conversion
        assert self.resolver.convert_type("a,b,c", list) == ["a", "b", "c"]
        assert self.resolver.convert_type("", list) == []

        # Dict conversion (JSON)
        json_str = '{"key": "value", "num": 42}'
        assert self.resolver.convert_type(json_str, dict) == {"key": "value", "num": 42}

    def test_convert_type_error(self):
        """Test type conversion errors."""
        with pytest.raises(TypeConversionError):
            self.resolver.convert_type("maybe", bool)

        with pytest.raises(TypeConversionError):
            self.resolver.convert_type("not_a_number", int)

        with pytest.raises(TypeConversionError):
            self.resolver.convert_type('{"invalid": json}', dict)

    def test_validate_variables(self):
        """Test variable validation."""
        # All variables valid
        errors = self.resolver.validate_variables(
            "${variables.api_key} and ${metadata.job_id}", self.context
        )
        assert len(errors) == 0

        # Missing variable
        errors = self.resolver.validate_variables("${variables.missing}", self.context)
        assert len(errors) > 0
        assert isinstance(errors[0], VariableNotFoundError)

    def test_type_conversion_in_substitution(self):
        """Test automatic type conversion during substitution."""
        context = VariableContext(
            job_variables={
                "count": "42",
                "price": "19.99",
                "enabled": "true",
                "items": '["a", "b", "c"]',
            }
        )

        data = {
            "count": "${variables.count}",
            "price": "${variables.price}",
            "enabled": "${variables.enabled}",
            "items": "${variables.items}",
        }

        result = self.resolver.substitute_in_dict(data, context, convert_types=True)

        assert result["count"] == 42
        assert isinstance(result["count"], int)
        assert result["price"] == 19.99
        assert isinstance(result["price"], float)
        assert result["enabled"] is True
        assert isinstance(result["enabled"], bool)
        assert result["items"] == ["a", "b", "c"]
        assert isinstance(result["items"], list)

    def test_context_strict_mode(self):
        """Test context strict mode override."""
        context = VariableContext(strict_mode=False)

        # Should not raise error even with missing variable
        result = self.resolver.substitute("Missing: ${variables.missing}", context)
        assert result == "Missing: ${variables.missing}"

        # Context strict mode should override resolver setting
        context_strict = VariableContext(strict_mode=True)

        with pytest.raises(VariableNotFoundError):
            self.resolver.substitute("Missing: ${variables.missing}", context_strict)


class TestDefaultResolver:
    """Test default resolver and convenience functions."""

    def test_substitute_function(self):
        """Test substitute convenience function."""
        context = VariableContext(job_variables={"key": "value"})
        result = substitute("${variables.key}", context)
        assert result == "value"

    def test_substitute_dict_function(self):
        """Test substitute_dict convenience function."""
        context = VariableContext(job_variables={"key": "value"})
        data = {"field": "${variables.key}"}
        result = substitute_dict(data, context)
        assert result == {"field": "value"}

    def test_get_variable_function(self):
        """Test get_variable convenience function."""
        context = VariableContext(job_variables={"key": "value"})
        result = get_variable("${variables.key}", context)
        assert result == "value"

    def test_validate_variables_function(self):
        """Test validate_variables convenience function."""
        context = VariableContext(job_variables={"key": "value"})
        errors = validate_variables("${variables.key}", context)
        assert len(errors) == 0

        errors = validate_variables("${variables.missing}", context)
        assert len(errors) > 0


class TestComplexScenarios:
    """Test complex variable substitution scenarios."""

    def test_url_with_query_parameters(self):
        """Test URL with multiple query parameters."""
        resolver = VariableResolver()
        context = VariableContext(
            job_variables={
                "api_key": "secret123",
                "base_url": "https://api.example.com",
                "version": "v2",
            },
            pagination_state={"current_page": 3},
            environment={"ENVIRONMENT": "production"},
        )

        url = (
            "${variables.base_url}/${variables.version}/search?"
            "api_key=${variables.api_key}&page=${pagination.current_page}"
            "&env=${ENV.ENVIRONMENT}"
        )

        result = resolver.substitute(url, context)
        expected = "https://api.example.com/v2/search?api_key=secret123&page=3&env=production"
        assert result == expected

    def test_json_configuration(self):
        """Test variable substitution in JSON configuration."""
        resolver = VariableResolver()
        context = VariableContext(
            job_variables={
                "username": "admin",
                "password": "secret",
                "database": {"name": "mydb", "host": "localhost"},
            },
            metadata={"job_id": "12345"},
        )

        config = {
            "database": {
                "user": "${variables.username}",
                "pass": "${variables.password}",
                "name": "${variables.database.name}",
                "host": "${variables.database.host}",
            },
            "job": {"id": "${metadata.job_id}"},
            "settings": {
                "debug": "true",
                "timeout": "30",
                "retries": "3",
            },
        }

        result = resolver.substitute_in_dict(config, context, convert_types=True)

        assert result["database"]["user"] == "admin"
        assert result["database"]["pass"] == "secret"
        assert result["database"]["name"] == "mydb"
        assert result["database"]["host"] == "localhost"
        assert result["job"]["id"] == 12345
        assert isinstance(result["job"]["id"], int)
        assert result["settings"]["debug"] is True
        assert result["settings"]["timeout"] == 30
        assert result["settings"]["retries"] == 3

    def test_crawl_configuration_example(self):
        """Test realistic crawl configuration example."""
        resolver = VariableResolver()
        context = VariableContext(
            job_variables={
                "api_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "target_domain": "https://example.com",
                "category_id": "technology",
                "date_from": "2025-01-01",
            },
            pagination_state={"current_page": 1},
            metadata={"job_id": "crawl-123", "website_id": "site-456"},
            environment={"PROXY_URL": "http://proxy.example.com:8080"},
        )

        crawl_config = {
            "url": "${variables.target_domain}/api/v1/articles",
            "method": "GET",
            "headers": {
                "Authorization": "Bearer ${variables.api_token}",
                "Accept": "application/json",
                "User-Agent": "LexiconCrawler/1.0",
            },
            "params": {
                "category": "${variables.category_id}",
                "date_from": "${variables.date_from}",
                "page": "${pagination.current_page}",
                "limit": "100",
            },
            "metadata": {
                "job_id": "${metadata.job_id}",
                "website_id": "${metadata.website_id}",
                "source": "api",
            },
            "proxy": "${ENV.PROXY_URL}",
            "rate_limit": {"requests_per_second": 2, "burst": 5},
        }

        result = resolver.substitute_in_dict(crawl_config, context, convert_types=True)

        # Verify substitutions
        assert result["url"] == "https://example.com/api/v1/articles"
        assert (
            result["headers"]["Authorization"] == "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
        )
        assert result["params"]["category"] == "technology"
        assert result["params"]["date_from"] == "2025-01-01"
        assert result["params"]["page"] == 1
        assert result["params"]["limit"] == 100
        assert result["metadata"]["job_id"] == "crawl-123"
        assert result["metadata"]["website_id"] == "site-456"
        assert result["proxy"] == "http://proxy.example.com:8080"

    def test_error_handling_scenarios(self):
        """Test various error handling scenarios."""
        resolver = VariableResolver()

        # Mixed valid and invalid variables
        context = VariableContext(job_variables={"valid": "value"}, strict_mode=False)
        text = "Valid: ${variables.valid}, Invalid: ${variables.invalid}, Unknown: ${unknown.var}"

        result = resolver.substitute(text, context)
        # Non-strict mode leaves invalid variables as-is
        assert "Valid: value" in result
        assert "${variables.invalid}" in result
        assert "${unknown.var}" in result

        # Test with strict mode
        context_strict = VariableContext(job_variables={"valid": "value"}, strict_mode=True)
        with pytest.raises(VariableNotFoundError):
            resolver.substitute(text, context_strict)

    def test_complex_nested_substitution(self):
        """Test complex nested variable substitutions."""
        resolver = VariableResolver()
        context = VariableContext(
            job_variables={
                "env": "prod",
                "api": {
                    "base": {
                        "prod": "https://api.prod.example.com",
                        "dev": "https://api.dev.example.com",
                    }
                },
                "endpoints": {
                    "users": "/users",
                    "posts": "/posts",
                },
                "version": "v1",
            },
        )

        # Test supported nested substitution
        # Note: Dynamic variable names like ${variables.api.base.${variables.env}}
        # are not supported. We use explicit paths instead.

        base_url = "${variables.api.base.prod}"
        version = "${variables.version}"
        endpoint = "${variables.endpoints.users}"

        # Build the URL step by step
        result = resolver.substitute(f"{base_url}/{version}{endpoint}", context)
        assert result == "https://api.prod.example.com/v1/users"

    def test_pagination_auto_increment(self):
        """Test pagination auto-increment scenario."""
        resolver = VariableResolver()

        # Simulate multiple pages
        for page in range(1, 4):
            context = VariableContext(
                pagination_state={"current_page": page},
                job_variables={"per_page": "20"},
            )

            url = "https://example.com/api/data?page=${pagination.current_page}&per_page=${variables.per_page}"
            result = resolver.substitute(url, context)
            expected = f"https://example.com/api/data?page={page}&per_page=20"
            assert result == expected
