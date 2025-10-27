# OpenAPI Code Generation

This document describes how to generate and use OpenAPI-based models and clients for the Lexicon Crawler API.

## Overview

The project uses OpenAPI 3.1.0 as the single source of truth for API contracts. From the OpenAPI specification (`openapi.yaml`), we generate:

1. **Pydantic models** for use in the FastAPI application
2. **Python client SDK** for consumers of the API
3. **TypeScript/JavaScript clients** (optional)
4. **Other language clients** as needed

## Architecture

```
openapi.yaml (Source of Truth)
    │
    ├─> Pydantic Models (datamodel-codegen)
    │   └─> crawler/api/generated/models.py
    │   └─> crawler/api/generated/extended.py (with validators)
    │
    └─> Python Client SDK (openapi-generator)
        └─> clients/python/
```

## Generating Models

### Prerequisites

- `datamodel-code-generator` - Installed as dev dependency
- `openapi-generator-cli` - Available globally via npm/asdf

### Generate Pydantic Models

```bash
# Using make command
make generate-models

# Or manually
uv run datamodel-codegen \
  --input openapi.yaml \
  --output crawler/api/generated/models.py \
  --input-file-type openapi \
  --output-model-type pydantic_v2.BaseModel \
  --use-standard-collections \
  --use-schema-description \
  --field-constraints \
  --use-default \
  --use-annotated \
  --use-double-quotes \
  --target-python-version 3.11
```

**Note**: After generating models, you may need to update `crawler/api/generated/extended.py` if there are breaking changes to the base models.

### Generate Python Client SDK

```bash
# Using make command
make generate-client

# Or manually
openapi-generator-cli generate \
  -i openapi.yaml \
  -g python \
  -o clients/python \
  --additional-properties=packageName=lexicon_crawler_client,packageVersion=1.0.0
```

### Validate OpenAPI Spec

```bash
# Using make command
make validate-openapi

# Or manually
openapi-generator-cli validate -i openapi.yaml
```

## Extended Models

The generated models in `crawler/api/generated/models.py` are pure auto-generated code. To add custom business logic validators, we use extended models in `crawler/api/generated/extended.py`:

### Extended Models Include:

1. **ScheduleConfig** - Ensures enum defaults instead of strings
2. **CrawlStep** - Validates `browser_type` is set when `method='browser'`
3. **CreateWebsiteRequest** - Validates:
   - `base_url` starts with `http://` or `https://`
   - Step names are unique
   - Provides default values for `schedule` and `global_config`

### Example Extended Model:

```python
class CrawlStep(_CrawlStep):
    """Extended CrawlStep with custom validators."""

    @model_validator(mode="after")
    def validate_browser_type(self) -> "CrawlStep":
        """Validate browser_type is set when method is browser."""
        if self.method == MethodEnum.browser and self.browser_type is None:
            raise ValueError("browser_type is required when method is 'browser'")
        return self
```

## Using Generated Models

### In the Application

```python
from crawler.api.generated import CreateWebsiteRequest, WebsiteResponse

# Models are automatically used by FastAPI
@router.post("/websites", response_model=WebsiteResponse)
async def create_website(request: CreateWebsiteRequest):
    # request is fully validated and type-safe
    pass
```

### Serializing to Database

When saving to the database, use `mode="json"` to properly serialize enums and URLs:

```python
config = {
    "schedule": request.schedule.model_dump(mode="json"),
    "steps": [step.model_dump(mode="json") for step in request.steps],
    "global_config": request.global_config.model_dump(mode="json"),
}
```

This ensures:
- Enums are serialized to their string values
- AnyUrl objects are converted to strings
- All data is JSON-compatible

## Using the Python Client SDK

### Installation

```bash
pip install -e clients/python/
```

### Basic Usage

```python
import lexicon_crawler_client
from lexicon_crawler_client import WebsitesApi, CreateWebsiteRequest, CrawlStep

# Configure client
configuration = lexicon_crawler_client.Configuration(
    host="https://crawler.lexicon.id"
)

# Create API instance
with lexicon_crawler_client.ApiClient(configuration) as api_client:
    api = WebsitesApi(api_client)

    # Create website
    request = CreateWebsiteRequest(
        name="Example Site",
        base_url="https://example.com",
        steps=[
            CrawlStep(
                name="crawl_list",
                type="crawl",
                method="http",
                selectors={"articles": ".article-link"}
            )
        ]
    )

    response = api.create_website(request)
    print(f"Created website: {response.id}")
    print(f"Next run time: {response.next_run_time}")
```

## Workflow

### When Updating the API

1. **Modify `openapi.yaml`** - Update the spec with new endpoints, models, or fields
2. **Validate**: `make validate-openapi`
3. **Generate models**: `make generate-models`
4. **Update extended models** - If breaking changes, update `crawler/api/generated/extended.py`
5. **Generate client**: `make generate-client` (optional, for consumers)
6. **Run tests**: `make test`
7. **Commit changes** - Include both `openapi.yaml` and generated files

### Version Compatibility

- OpenAPI spec version in `openapi.yaml` → Application version
- Generated models are automatically versioned with the application
- Client SDK version is set via `--additional-properties=packageVersion=X.Y.Z`

## Benefits of This Approach

1. **Single Source of Truth** - OpenAPI spec defines everything
2. **Type Safety** - Auto-generated Pydantic models ensure type correctness
3. **Consistency** - Server and client always match the spec
4. **Documentation** - OpenAPI spec serves as API documentation
5. **Client Generation** - Automatic SDK generation for any language
6. **Validation** - Pydantic validates all inputs/outputs automatically

## Common Issues

### Issue: Enum values are strings instead of enum objects

**Solution**: Use extended models with proper enum defaults (already implemented)

### Issue: AnyUrl adds trailing slashes

**Expected behavior**: This is standard URL normalization. Update tests to expect the normalized form.

### Issue: Custom validators not firing

**Solution**: Ensure extended models override the base generated models and are properly exported in `__init__.py`

### Issue: JSON serialization fails with enums

**Solution**: Use `model_dump(mode="json")` instead of `model_dump()`

## Future Improvements

- Add more language clients (Go, Java, TypeScript)
- Automate client publishing to package repositories
- Add contract testing between spec and implementation
- Generate API documentation website from OpenAPI spec

## Tool Configuration

### Excluding Generated Code from Linters

The generated code is automatically excluded from ruff and mypy in `pyproject.toml`:

**Ruff Configuration:**
```toml
[tool.ruff]
exclude = [
    "crawler/db/generated",      # sqlc-generated database code
    "crawler/api/generated",     # OpenAPI-generated models
    "clients/python",            # Generated Python client SDK
]
```

**Mypy Configuration:**
```toml
[tool.mypy]
exclude = [
    "^crawler/db/generated/.*\\.py$",
    "^crawler/api/generated/.*\\.py$",
    "^clients/python/.*\\.py$",
]
```

**Note:** The `__init__.py` and `extended.py` files in `crawler/api/generated/` are NOT auto-generated and will still be checked by linters. These files contain our custom logic and should follow project style guidelines.

### Git Ignore

Generated files are excluded from version control in `.gitignore`:

```gitignore
# Generated code from OpenAPI/sqlc
crawler/api/generated/models.py
clients/python/
```

**What gets committed:**
- ✅ `openapi.yaml` - Source of truth
- ✅ `crawler/api/generated/__init__.py` - Custom exports
- ✅ `crawler/api/generated/extended.py` - Custom validators
- ❌ `crawler/api/generated/models.py` - Auto-generated (can be regenerated)
- ❌ `clients/python/` - Auto-generated client SDK

This ensures the repository stays clean while keeping the necessary custom code under version control.
