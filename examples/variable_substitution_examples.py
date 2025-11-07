"""Variable Substitution Examples

This file demonstrates practical usage of the variable substitution system
in various crawling scenarios.
"""

import json
import traceback
from uuid import uuid4

from crawler.utils.variable_substitution import (
    VariableContext,
    VariableResolver,
)


def example_1_basic_api_crawling():
    """Example 1: Basic API crawling with authentication."""
    print("=" * 60)
    print("Example 1: Basic API Crawling")
    print("=" * 60)

    resolver = VariableResolver()

    # Define context with API credentials
    context = VariableContext(
        job_variables={
            "api_base": "https://jsonplaceholder.typicode.com",
            "api_key": "demo-key-12345",
            "version": "v1",
            "timeout": "30",
        },
        metadata={
            "job_id": f"job-{uuid4().hex[:8]}",
            "website_id": "jsonplaceholder",
            "created_by": "crawler@example.com",
        },
    )

    # Configuration template
    config_template = {
        "url": "${variables.api_base}/${variables.version}/posts",
        "method": "GET",
        "headers": {
            "Authorization": "Bearer ${variables.api_key}",
            "Accept": "application/json",
            "User-Agent": "LexiconCrawler/1.0",
            "X-Job-ID": "${metadata.job_id}",
        },
        "params": {
            "limit": "10",
            "timeout": "${variables.timeout}",
        },
        "rate_limit": {"requests_per_second": 5},
    }

    # Perform substitution
    config = resolver.substitute_in_dict(config_template, context, convert_types=True)

    print("Resolved Configuration:")
    print(json.dumps(config, indent=2))
    print()


def example_2_ecommerce_pagination():
    """Example 2: E-commerce site with pagination."""
    print("=" * 60)
    print("Example 2: E-commerce with Pagination")
    print("=" * 60)

    resolver = VariableResolver()

    # Simulate crawling multiple pages
    for page in range(1, 4):
        context = VariableContext(
            job_variables={
                "base_url": "https://fakestoreapi.com",
                "category": "electronics",
                "sort": "price",
                "order": "asc",
            },
            pagination_state={
                "current_page": page,
                "page_size": 5,
                "offset": (page - 1) * 5,
            },
            metadata={"page": page, "total_pages": 3},
        )

        config = {
            "url": "${variables.base_url}/products",
            "params": {
                "category": "${variables.category}",
                "sort": "${variables.sort}",
                "order": "${variables.order}",
                "limit": "${pagination.page_size}",
                "skip": "${pagination.offset}",
            },
            "headers": {
                "X-Page": "${metadata.page}",
                "X-Total-Pages": "${metadata.total_pages}",
            },
        }

        result = resolver.substitute_in_dict(config, context, convert_types=True)

        print(f"Page {page} Configuration:")
        print(f"URL: {result['url']}?category={result['params']['category']}")
        print(f"  Parameters: {result['params']}")
        print(f"  Headers: {result['headers']}")
        print()


def example_3_environment_variables():
    """Example 3: Using environment variables."""
    print("=" * 60)
    print("Example 3: Environment Variables")
    print("=" * 60)

    resolver = VariableResolver()

    # Simulate environment variables from database and OS
    context = VariableContext(
        job_variables={
            "endpoint": "/api/data",
            "format": "json",
        },
        environment={
            "API_HOST": "https://api.service.com",
            "API_PORT": "443",
            "DB_CONFIG": {
                "host": "localhost",
                "port": 5432,
                "name": "crawler_db",
            },
            "SECRETS": {
                "api_key": "sk-1234567890",
                "webhook_secret": "whsec_abcdef123456",
            },
        },
        allow_env_fallback=False,  # Only use provided environment
    )

    configs = [
        {
            "name": "API Request",
            "url": "${ENV.API_HOST}${variables.endpoint}",
            "port": "${ENV.API_PORT}",
            "format": "${variables.format}",
        },
        {
            "name": "Database Connection",
            "host": "${ENV.DB_CONFIG.host}",
            "port": "${ENV.DB_CONFIG.port}",
            "database": "${ENV.DB_CONFIG.name}",
        },
        {
            "name": "Authenticated Request",
            "url": "${ENV.API_HOST}/protected",
            "headers": {
                "Authorization": "Bearer ${ENV.SECRETS.api_key}",
                "X-Webhook-Secret": "${ENV.SECRETS.webhook_secret}",
            },
        },
    ]

    for config_template in configs:
        config = resolver.substitute_in_dict(config_template, context, convert_types=True)
        print(f"{config_template['name']}:")
        print(json.dumps(config, indent=2))
        print()


def example_4_multi_step_workflow():
    """Example 4: Multi-step workflow with input/output passing."""
    print("=" * 60)
    print("Example 4: Multi-step Workflow")
    print("=" * 60)

    resolver = VariableResolver()

    # Step 1: Extract categories
    step1_output = {
        "categories": ["technology", "business", "science"],
        "total_categories": 3,
        "metadata": {"extraction_time": "2025-01-01T12:00:00Z"},
    }

    # Step 2: Use output from step 1
    context = VariableContext(
        job_variables={
            "base_url": "https://newsapi.org/v2",
            "api_key": "demo-key",
            "page_size": 20,
        },
        step_input=step1_output,
        metadata={
            "workflow_id": f"wf-{uuid4().hex[:8]}",
            "current_step": 2,
            "total_steps": 3,
        },
    )

    # Generate URLs for each category
    configs = []
    for category in step1_output["categories"]:
        config = {
            "url": "${variables.base_url}/top-headlines",
            "params": {
                "category": category,
                "pageSize": "${variables.page_size}",
                "apiKey": "${variables.api_key}",
            },
            "metadata": {
                "workflow_id": "${metadata.workflow_id}",
                "step": "${metadata.current_step}",
                "category": category,
                "total_categories": "${input.total_categories}",
            },
        }
        configs.append(config)

    # Substitute all configurations
    results = resolver.substitute_in_dict({"category_configs": configs}, context)

    print("Step 2 - Fetching headlines for each category:")
    for i, config in enumerate(results["category_configs"]):
        category = step1_output["categories"][i]
        print(f"\n{category.title()}:")
        print(f"  URL: {config['url']}")
        params = config["params"]
        print(f"  Params: category={params['category']}, pageSize={params['pageSize']}")
        metadata = config["metadata"]
        print(f"  Metadata: workflow={metadata['workflow_id']}, step={metadata['step']}")
    print()


def example_5_type_conversion():
    """Example 5: Type conversion and validation."""
    print("=" * 60)
    print("Example 5: Type Conversion")
    print("=" * 60)

    resolver = VariableResolver()

    context = VariableContext(
        job_variables={
            "max_items": "100",
            "enable_cache": "true",
            "price_limit": "99.99",
            "tags": "python,api,crawler,web-scraping",
            "config": '{"retry_attempts": 3, "timeout": 30}',
            "empty_list": "",
            "zero": "0",
        },
    )

    data = {
        "settings": {
            "max_items": "${variables.max_items}",
            "enable_cache": "${variables.enable_cache}",
            "price_limit": "${variables.price_limit}",
            "retry_zero": "${variables.zero}",
        },
        "tags": "${variables.tags}",
        "config": "${variables.config}",
        "empty": "${variables.empty_list}",
    }

    # Substitute with type conversion
    result = resolver.substitute_in_dict(data, context, convert_types=True)

    print("Type Conversion Results:")
    settings = result["settings"]
    print(f"max_items: {settings['max_items']} (type: {type(settings['max_items']).__name__})")
    cache_val = settings["enable_cache"]
    print(f"enable_cache: {cache_val} (type: {type(cache_val).__name__})")
    print(
        f"price_limit: {settings['price_limit']} (type: {type(settings['price_limit']).__name__})"
    )
    print(f"retry_zero: {settings['retry_zero']} (type: {type(settings['retry_zero']).__name__})")
    print(f"tags: {result['tags']} (type: {type(result['tags']).__name__})")
    print(f"config: {result['config']} (type: {type(result['config']).__name__})")
    print(f"empty: {result['empty']} (type: {type(result['empty']).__name__})")
    print()


def example_6_error_handling():
    """Example 6: Error handling scenarios."""
    print("=" * 60)
    print("Example 6: Error Handling")
    print("=" * 60)

    # Strict mode - raises errors for missing variables
    print("1. Strict Mode (Default):")
    resolver_strict = VariableResolver(strict_mode=True)
    context = VariableContext(job_variables={"existing": "value"})

    try:
        result = resolver_strict.substitute("Missing: ${variables.missing}", context)
    except Exception as e:
        print(f"   Error: {type(e).__name__}: {e}")

    # Non-strict mode - preserves missing variables
    print("\n2. Non-Strict Mode:")
    resolver_lenient = VariableResolver(strict_mode=False)
    context.strict_mode = False
    result = resolver_lenient.substitute("Prefix ${variables.missing} suffix", context)
    print(f"   Result: {result}")

    # Circular reference detection
    print("\n3. Circular Reference Detection:")
    context_circular = VariableContext(
        job_variables={"var1": "${variables.var2}", "var2": "${variables.var1}"}
    )

    try:
        result = resolver_strict.substitute("${variables.var1}", context_circular)
    except Exception as e:
        print(f"   Error: {type(e).__name__}: {e}")

    # Type conversion errors
    print("\n4. Type Conversion (graceful fallback):")
    context = VariableContext(job_variables={"invalid_bool": "maybe"})
    data = {"value": "${variables.invalid_bool}"}
    result = resolver_strict.substitute_in_dict(data, context, convert_types=True)
    print(f"   Invalid boolean 'maybe' falls back to string: {result['value']}")
    print()


def example_7_real_world_crawl_config():
    """Example 7: Complete real-world crawl configuration."""
    print("=" * 60)
    print("Example 7: Real-World Crawl Configuration")
    print("=" * 60)

    resolver = VariableResolver()

    # Complex scenario: API with authentication, pagination, and data processing
    context = VariableContext(
        job_variables={
            "api": {
                "base_url": "https://api.github.com",
                "token": "ghp_demo_token_12345",
                "version": "2022-11-28",
            },
            "repository": {
                "owner": "octocat",
                "name": "Hello-World",
            },
            "query": {
                "state": "open",
                "sort": "created",
                "direction": "desc",
                "per_page": 50,
            },
            "headers": {
                "accept": "application/vnd.github.v3+json",
                "user_agent": "LexiconCrawler/1.0",
            },
        },
        pagination_state={
            "current_page": 1,
            "page_size": 50,
            "max_pages": 10,
        },
        metadata={
            "job_id": f"github-crawl-{uuid4().hex[:8]}",
            "job_type": "repository_issues",
            "priority": "normal",
            "created_at": "2025-01-01T12:00:00Z",
        },
        environment={
            "PROXY_URL": "http://proxy.company.com:8080",
            "RATE_LIMIT": 5000,
        },
    )

    # Complex crawl configuration
    crawl_config = {
        "name": "GitHub Repository Issues Crawler",
        "version": "1.0",
        # Request configuration
        "request": {
            "url": (
                "${variables.api.base_url}/repos/"
                "${variables.repository.owner}/${variables.repository.name}/issues"
            ),
            "method": "GET",
            "headers": {
                "Authorization": "token ${variables.api.token}",
                "Accept": "${variables.headers.accept}",
                "User-Agent": "${variables.headers.user_agent}",
                "X-GitHub-Api-Version": "${variables.api.version}",
                "X-Job-ID": "${metadata.job_id}",
            },
            "params": {
                "state": "${variables.query.state}",
                "sort": "${variables.query.sort}",
                "direction": "${variables.query.direction}",
                "page": "${pagination.current_page}",
                "per_page": "${pagination.page_size}",
            },
            "proxy": "${ENV.PROXY_URL}",
            "timeout": 30,
        },
        # Rate limiting
        "rate_limiting": {
            "requests_per_hour": "${ENV.RATE_LIMIT}",
            "burst_size": 10,
            "backoff_strategy": "exponential",
        },
        # Pagination configuration
        "pagination": {
            "type": "page",
            "current_page": "${pagination.current_page}",
            "max_pages": "${pagination.max_pages}",
            "page_size_param": "per_page",
            "page_number_param": "page",
        },
        # Data extraction
        "extraction": {
            "fields": [
                "id",
                "title",
                "body",
                "state",
                "created_at",
                "updated_at",
                "user.login",
                "labels[*].name",
            ],
            "transformations": {
                "body": "clean_html",
                "created_at": "parse_iso8601",
                "labels": "split_by_comma",
            },
        },
        # Storage configuration
        "storage": {
            "type": "database",
            "table": "github_issues",
            "batch_size": 100,
            "metadata": {
                "job_id": "${metadata.job_id}",
                "job_type": "${metadata.job_type}",
                "repository": "${variables.repository.owner}/${variables.repository.name}",
            },
        },
        # Notifications
        "notifications": {
            "on_completion": {
                "webhook": "https://hooks.slack.com/...",
                "payload": {
                    "text": "Crawl completed for job ${metadata.job_id}",
                    "repository": "${variables.repository.owner}/${variables.repository.name}",
                    "total_issues": "150",  # Simulated output
                },
            },
        },
    }

    # Resolve the configuration
    resolved_config = resolver.substitute_in_dict(crawl_config, context, convert_types=True)

    print("Resolved Crawl Configuration:")
    print(f"Job ID: {resolved_config['metadata']['job_id']}")

    # Extract repository from URL
    url_parts = resolved_config["request"]["url"].split("/")
    repo = f"{url_parts[-3]}/{url_parts[-2]}"
    print(f"Repository: {repo}")

    print(f"Request URL: {resolved_config['request']['url']}")
    print(f"Rate Limit: {resolved_config['rate_limiting']['requests_per_hour']} requests/hour")

    pagination = resolved_config["pagination"]
    print(f"Pagination: Page {pagination['current_page']} of max {pagination['max_pages']}")
    print(f"Proxy: {resolved_config['request']['proxy']}")
    print("\nRequest Headers:")
    for k, v in resolved_config["request"]["headers"].items():
        if k == "Authorization":
            print(f"  {k}: token [REDACTED]")
        else:
            print(f"  {k}: {v}")
    print("\nRequest Parameters:")
    for k, v in resolved_config["request"]["params"].items():
        print(f"  {k}: {v}")
    print()


def example_8_dynamic_variable_building():
    """Example 8: Building dynamic variables."""
    print("=" * 60)
    print("Example 8: Dynamic Variable Building")
    print("=" * 60)

    resolver = VariableResolver()

    # Build dynamic configuration based on environment
    environments = {
        "dev": {
            "api_url": "https://dev-api.example.com",
            "debug": "true",
            "log_level": "debug",
        },
        "staging": {
            "api_url": "https://staging-api.example.com",
            "debug": "true",
            "log_level": "info",
        },
        "prod": {
            "api_url": "https://api.example.com",
            "debug": "false",
            "log_level": "error",
        },
    }

    for env, config in environments.items():
        context = VariableContext(
            job_variables={
                "environment": env,
                "api_url": config["api_url"],
                "debug": config["debug"],
                "log_level": config["log_level"],
                "service_name": "data-crawler",
            },
            metadata={"environment": env},
        )

        dynamic_config = {
            "service": "${variables.service_name}",
            "environment": "${variables.environment}",
            "api": {
                "base_url": "${variables.api_url}",
                "timeout": 30 if env == "prod" else 60,
                "retries": 3 if env == "prod" else 1,
            },
            "logging": {
                "level": "${variables.log_level}",
                "debug": "${variables.debug}",
            },
        }

        result = resolver.substitute_in_dict(dynamic_config, context, convert_types=True)

        print(f"{env.upper()} Environment:")
        print(f"  API URL: {result['api']['base_url']}")
        debug_val = result["logging"]["debug"]
        print(f"  Debug: {debug_val} (type: {type(debug_val).__name__})")
        print(f"  Log Level: {result['logging']['level']}")
        print(f"  Timeout: {result['api']['timeout']}s")
        print()


def main() -> None:
    """Run all examples."""
    print("Variable Substitution System Examples")
    print("=" * 60)
    print()

    examples = [
        example_1_basic_api_crawling,
        example_2_ecommerce_pagination,
        example_3_environment_variables,
        example_4_multi_step_workflow,
        example_5_type_conversion,
        example_6_error_handling,
        example_7_real_world_crawl_config,
        example_8_dynamic_variable_building,
    ]

    for example in examples:
        try:
            example()
        except Exception as e:
            print(f"Error in {example.__name__}: {e}")
            traceback.print_exc()
        print()


if __name__ == "__main__":
    main()
