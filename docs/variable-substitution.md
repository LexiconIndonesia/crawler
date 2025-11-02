# Variable Substitution System

The Lexicon Crawler includes a powerful variable substitution system that allows you to create dynamic and configurable crawling jobs. Variables can be used in URLs, headers, parameters, and other configuration values.

## Overview

The variable substitution system supports multiple variable sources:

- **`${variables.key}`** - Job submission variables (with overrides)
- **`${ENV.KEY}`** - Environment variables (from database or OS)
- **`${input.field}`** - Output from previous crawl step
- **`${pagination.current_page}`** - Auto-incremented page counter
- **`${metadata.field}`** - Job metadata fields

## Quick Start

### Basic Variable Usage

```python
from crawler.utils.variable_substitution import VariableResolver, VariableContext

# Create resolver
resolver = VariableResolver()

# Define context with variables
context = VariableContext(
    job_variables={
        "api_key": "secret123",
        "base_url": "https://api.example.com",
    },
    metadata={"job_id": "crawl-001"},
)

# Substitute variables in string
url = resolver.substitute(
    "${variables.base_url}/v1/data?api_key=${variables.api_key}",
    context
)
# Result: https://api.example.com/v1/data?api_key=secret123
```

### Using with Dictionaries

```python
config = {
    "url": "${variables.base_url}/api",
    "headers": {
        "Authorization": "Bearer ${variables.api_key}",
        "X-Job-ID": "${metadata.job_id}",
    },
    "params": {
        "page": "${pagination.current_page}",
        "limit": "100",
    },
}

result = resolver.substitute_in_dict(config, context, convert_types=True)
```

## Variable Sources

### 1. Job Variables (`${variables.*}`)

These are the primary variables defined in job submissions or website configurations.

```json
{
  "variables": {
    "api_key": "your-api-key",
    "base_url": "https://api.example.com",
    "endpoints": {
      "users": "/users",
      "posts": "/posts"
    }
  }
}
```

Usage:
- `${variables.api_key}` → `"your-api-key"`
- `${variables.endpoints.users}` → `"/users"`

### 2. Environment Variables (`${ENV.*}`)

Environment variables stored in the database or from the OS environment.

```python
context = VariableContext(
    environment={
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "API_KEYS": {
            "service1": "key1",
            "service2": "key2"
        }
    },
    allow_env_fallback=True  # Also check os.environ
)
```

Usage:
- `${ENV.DB_HOST}` → `"localhost"`
- `${ENV.API_KEYS.service1}` → `"key1"`

### 3. Input Variables (`${input.*}`)

Output from the previous crawl step in a multi-step workflow.

```python
context = VariableContext(
    step_input={
        "total_items": 150,
        "next_page_token": "abc123",
        "extracted_data": {
            "categories": ["tech", "science"],
            "latest_date": "2025-01-01"
        }
    }
)
```

Usage:
- `${input.total_items}` → `150`
- `${input.extracted_data.categories}` → `["tech", "science"]`

### 4. Pagination Variables (`${pagination.*}`)

Built-in and custom pagination variables.

```python
context = VariableContext(
    pagination_state={
        "current_page": 5,
        "cursor": "page5_marker",
        "has_next": True
    }
)
```

Built-in variables:
- `${pagination.current_page}` → Current page number (default: 1)
- `${pagination.page_size}` → Items per page (default: 10)
- `${pagination.total_pages}` → Total pages (default: 0)
- `${pagination.total_items}` → Total items (default: 0)
- `${pagination.offset}` → Current offset (default: 0)

Custom variables:
- `${pagination.cursor}` → Custom cursor value
- `${pagination.has_next}` → Boolean flag

### 5. Metadata Variables (`${metadata.*}`)

Job metadata fields.

```python
context = VariableContext(
    metadata={
        "job_id": "crawl-001",
        "website_id": "site-123",
        "created_by": "user@example.com",
        "tags": ["api", "v2", "production"]
    }
)
```

Usage:
- `${metadata.job_id}` → `"crawl-001"`
- `${metadata.tags}` → `["api", "v2", "production"]`

## Type Conversion

The system can automatically convert string values to appropriate types:

```python
context = VariableContext(
    job_variables={
        "count": "42",
        "price": "19.99",
        "enabled": "true",
        "items": '["a", "b", "c"]',
        "config": '{"key": "value"}'
    }
)

data = {
    "count": "${variables.count}",
    "price": "${variables.price}",
    "enabled": "${variables.enabled}",
    "items": "${variables.items}",
    "config": "${variables.config}"
}

result = resolver.substitute_in_dict(data, context, convert_types=True)

# Conversions:
# "42" → 42 (int)
# "19.99" → 19.99 (float)
# "true" → True (bool)
# '["a", "b", "c"]' → ["a", "b", "c"] (list)
# '{"key": "value"}' → {"key": "value"} (dict)
```

### Supported Conversions

**Automatic type conversion** (when `convert_types=True`):

- **Boolean**: `"true"`, `"false"` → `True`, `False`
- **Integer**: Whole numbers, handles `"3.0"` → `3`
- **Float**: Decimal numbers, e.g., `"19.99"` → `19.99`
- **List**: JSON array strings, e.g., `'["a", "b", "c"]'` → `["a", "b", "c"]`
- **Dict**: JSON object strings, e.g., `'{"key": "value"}'` → `{"key": "value"}`

**Explicit type conversion** (when using `convert_type(value, target_type)`):

- Same as above, plus:
- **List from comma-separated**: `"a, b, c"` → `["a", "b", "c"]` (only with explicit `target_type=list`)

## Error Handling

### Strict Mode (Default)

Missing variables raise `VariableNotFoundError`:

```python
resolver = VariableResolver(strict_mode=True)  # Default
context = VariableContext(job_variables={"existing": "value"})

# This will raise VariableNotFoundError
resolver.substitute("${variables.missing}", context)
```

### Non-Strict Mode

Missing variables are left unchanged:

```python
resolver = VariableResolver(strict_mode=False)
context = VariableContext(job_variables={"existing": "value"})

result = resolver.substitute("Prefix ${variables.missing} suffix", context)
# Result: "Prefix ${variables.missing} suffix"
```

### Circular Reference Detection

The system detects and prevents circular references:

```python
context = VariableContext(
    job_variables={"var1": "${variables.var2}", "var2": "${variables.var1}"}
)

# Raises CircularReferenceError
resolver.substitute("${variables.var1}", context)
```

## Advanced Features

### Escaping Variables

Use backslash to escape variable references:

```python
text = r"Literal: \${variables.api_key}, Substituted: ${variables.api_key}"
result = resolver.substitute(text, context)
# Result: "Literal: ${variables.api_key}, Substituted: secret123"
```

### Recursive Substitution

Variables can reference other variables:

```python
context = VariableContext(
    job_variables={
        "base_url": "https://api.example.com",
        "api_endpoint": "${variables.base_url}/v1",
        "full_url": "${variables.api_endpoint}/data"
    }
)

result = resolver.substitute("${variables.full_url}", context)
# Result: "https://api.example.com/v1/data"
```

### Variable Validation

Validate that all variables in a template can be resolved:

```python
errors = resolver.validate_variables("${variables.api_key}/${variables.missing}", context)
# Returns list of VariableNotFoundError for missing variables
```

### Listing Available Variables

List all available variables by source:

```python
available = resolver.list_available_variables(context)
# Returns:
# {
#     "variables": ["api_key", "base_url"],
#     "ENV": ["DB_HOST", "API_KEY"],
#     "pagination": ["current_page", "page_size"],
#     "metadata": ["job_id"],
#     "input": []
# }
```

## Real-World Examples

### API Crawling with Authentication

```python
context = VariableContext(
    job_variables={
        "api_base": "https://api.github.com",
        "token": "ghp_xxxxxxxxxxxx",
        "repo": "owner/repo"
    },
    metadata={"job_id": "github-crawl-001"},
    environment={"PROXY": "http://proxy.company.com:8080"}
)

config = {
    "url": "${variables.api_base}/repos/${variables.repo}/issues",
    "headers": {
        "Authorization": "token ${variables.token}",
        "User-Agent": "LexiconCrawler/1.0",
        "X-Job-ID": "${metadata.job_id}"
    },
    "params": {
        "state": "open",
        "per_page": "100"
    },
    "proxy": "${ENV.PROXY}"
}

result = resolver.substitute_in_dict(config, context)
```

### E-commerce Site with Pagination

```python
for page in range(1, 4):
    context = VariableContext(
        job_variables={
            "base_url": "https://shop.example.com",
            "category": "electronics"
        },
        pagination_state={"current_page": page},
        step_input={"total_products": 150}
    )

    config = {
        "url": "${variables.base_url}/api/products",
        "params": {
            "category": "${variables.category}",
            "page": "${pagination.current_page}",
            "limit": "20"
        },
        "headers": {"X-Total-Products": "${input.total_products}"}
    }

    result = resolver.substitute_in_dict(config, context, convert_types=True)
```

### Multi-Source News Aggregation

```python
context = VariableContext(
    job_variables={
        "api_key": "your-newsapi-key",
        "sources": {
            "cnn": "https://edition.cnn.com",
            "bbc": "https://www.bbc.com"
        },
        "topics": ["technology", "business"]
    },
    metadata={"aggregation_id": "agg-001"},
    environment={"NEWS_API_URL": "https://newsapi.org/v2"}
)

# Generate configurations for each source and topic
configs = []
for source in context.job_variables["sources"]:
    for topic in context.job_variables["topics"]:
        config = {
            "url": "${ENV.NEWS_API_URL}/everything",
            "params": {
                "sources": source,
                "q": topic,
                "apiKey": "${variables.api_key}"
            },
            "metadata": {
                "aggregation_id": "${metadata.aggregation_id}",
                "source": source,
                "topic": topic
            }
        }
        configs.append(config)

result = resolver.substitute_in_dict({"configs": configs}, context)
```

## Integration with API

### Creating Website with Variables

```bash
curl -X POST http://localhost:8000/api/v1/websites \
  -H "Content-Type: application/json" \
  -d '{
    "name": "API Example",
    "base_url": "https://api.example.com",
    "method": "api",
    "config": {
      "api": {
        "url": "${variables.base_url}/v1/data",
        "headers": {
          "Authorization": "Bearer ${variables.api_key}"
        }
      }
    },
    "variables": {
      "base_url": "https://api.example.com",
      "api_key": "your-api-key"
    }
  }'
```

### Creating Job with Variable Overrides

```bash
curl -X POST http://localhost:8000/api/v1/crawl-jobs \
  -H "Content-Type: application/json" \
  -d '{
    "website_id": "website-uuid",
    "seed_url": "https://api.example.com/v1/search",
    "variables": {
      "api_key": "job-specific-key",
      "search_query": "python programming"
    }
  }'
```

## Best Practices

1. **Use descriptive variable names**: `api_key` instead of `k`
2. **Group related variables**: Use nested objects for organization
3. **Set appropriate strict mode**: Use strict mode in production
4. **Handle type conversion**: Enable `convert_types=True` for automatic conversion
5. **Validate variables**: Use `validate_variables()` before critical operations
6. **Document variables**: Include clear documentation for expected variables
7. **Use environment variables**: For sensitive data like API keys and passwords
8. **Limit recursion depth**: Set reasonable `max_recursion_depth` to prevent infinite loops

## Performance Considerations

- Variable substitution is fast but has overhead for complex nested structures
- Circular reference detection adds minimal overhead
- Type conversion happens once per variable
- Consider caching resolved configurations for repeated use
- Use non-strict mode during development for faster iteration

## Troubleshooting

### Common Issues

1. **Variable not found**: Check variable names and context
2. **Type conversion failed**: Verify input format matches expected type
3. **Circular reference**: Review variable dependencies
4. **Missing environment variable**: Check database or OS environment
5. **Recursive depth exceeded**: Simplify variable dependencies

### Debugging

```python
# List available variables
available = resolver.list_available_variables(context)
print("Available variables:", available)

# Validate variables
errors = resolver.validate_variables(template, context)
if errors:
    print("Variable errors:", errors)

# Check specific variable
value = resolver.get_variable("${variables.api_key}", context, default="NOT_FOUND")
print("Variable value:", value)
```
