# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lexicon Crawler is a production-ready web crawler built with FastAPI and modern Python async patterns. It combines browser automation (Playwright, undetected-chromedriver) with distributed task queuing (NATS JetStream), persistent storage (PostgreSQL + GCS), and full observability (Prometheus, Grafana, Loki).

## Current Development Status

**Active Branch**: `feature/implements-api-scheduling`

This branch implements:
- ✅ **Website API** (`/api/v1/websites`) - Create and manage website configurations
- ✅ **Scheduled Crawling** - Cron-based recurring crawls with pause/resume capability
- ✅ **OpenAPI Contract Testing** - Automated validation that FastAPI matches `openapi.yaml`
- ✅ **Contract-First Development** - `openapi.yaml` as single source of truth for API contracts
- ✅ **API Versioning** - API v1 with proper operation IDs and semantic versioning

### Key Features in This Branch

**1. Website Management API**
- POST `/api/v1/websites` - Create website with multi-step crawl/scrape configuration
- Support for API, Browser (Playwright/undetected-chrome), and HTTP methods
- Built-in selectors for data extraction (CSS/XPath)
- Global configuration for rate limits, timeouts, retries
- Automatic validation of cron expressions and configuration

**2. Scheduled Crawling**
- Cron-based scheduling (default: bi-weekly on 1st and 15th)
- `scheduled_job` table with `is_active` flag for pause/resume
- Automatic next run time calculation
- Per-job configuration overrides via JSONB `job_config`
- Optimized composite index on `(is_active, next_run_time)`

**3. Contract-First OpenAPI Development**
- `openapi.yaml` defines API contract (single source of truth)
- Pydantic models auto-generated from OpenAPI spec via `datamodel-codegen`
- Client SDK generation for frontend/external consumers
- Automated contract tests verify FastAPI matches spec (14 tests)
- CI validation of OpenAPI spec on every PR

**4. Type-Safe Code Generation**
- OpenAPI → Pydantic models (`make generate-models`)
- SQL → Python queries via sqlc (`make sqlc-generate`)
- Extended models in `crawler/api/generated/extended.py` for custom validators

## Development Commands

### OpenAPI Code Generation
```bash
make validate-openapi   # Validate OpenAPI specification
make generate-models    # Generate Pydantic models from OpenAPI
make generate-client    # Generate Python client SDK
make generate-all       # Validate + generate everything
```

### Setup
```bash
make setup              # Complete setup: deps + playwright + .env
make install-dev        # Install dev dependencies via uv
make playwright         # Install Playwright browsers
```

### Running the Application
```bash
make dev                # Start dev server with auto-reload (also starts db services)
make run                # Production server (single worker)
make run-prod           # Production server (4 workers)
```

### Testing
```bash
make test               # All tests
make test-unit          # Unit tests only
make test-integration   # Integration tests only
make test-cov           # With coverage report
make test-watch         # Watch mode
uv run pytest path/to/test.py::test_function  # Run specific test
```

### Code Quality
```bash
make format             # Format with ruff
make lint               # Lint check
make lint-fix           # Lint with auto-fix
make type-check         # Run mypy type checking
make check              # All checks (format + lint + type-check)
```

### Services
```bash
make db-up              # Start PostgreSQL, Redis, NATS
make docker-up          # Start all services (app + databases + monitoring)
make docker-down        # Stop all services
make db-shell           # Connect to PostgreSQL
make redis-shell        # Connect to Redis CLI
make monitoring-up      # Start Prometheus, Grafana, Loki
make urls               # List all service URLs
```

### Utilities
```bash
make clean              # Remove caches, pyc files, coverage reports
make encode-gcs FILE=path/to/creds.json  # Encode GCS credentials to base64
```

## Architecture

### Core Components

**FastAPI Application** (`main.py`, `crawler/api/`)
- Application factory pattern with `create_app()`
- Lifespan context manager for startup/shutdown
- API routes defined in `crawler/api/routes.py`
- CORS middleware enabled for all origins

**Configuration** (`config/settings.py`)
- Pydantic Settings-based configuration
- All settings loaded from environment variables or `.env` file
- Cached with `@lru_cache` decorator (`get_settings()`)
- Environment-aware: development/staging/production

**Database Layer** (`crawler/db/`)
- **SQL schema as single source of truth**: `sql/schema/*.sql` defines all tables and types
- **sqlc** generates type-safe Python code from SQL queries
- **Repository pattern** provides clean interfaces over sqlc-generated code
- SQLAlchemy 2.0 for connections and sessions only (asyncpg driver)
- Async session factory in `session.py`, connection pooling via settings
- SQL queries in `sql/queries/*.sql`, schema in `sql/schema/*.sql`
- Generated code in `crawler/db/generated/` (never edit manually)
- Repositories in `crawler/db/repositories.py` handle JSON serialization and parameter mapping
- **Core tables**: `website`, `crawl_job`, `crawled_page`, `content_hash`, `crawl_log`, `scheduled_job`
- **Scheduled jobs**: Websites can have default cron schedules; `scheduled_job` table tracks recurring crawls with `is_active` flag for pausing

**Services** (`crawler/services/`)
- `CacheService`: Redis-based caching for URL deduplication and rate limiting
- `StorageService`: GCS for raw HTML storage with base64-encoded credentials
- All services use async/await patterns

**Observability** (`crawler/core/`)
- `logging.py`: structlog for structured JSON logging
- `metrics.py`: Prometheus metrics (HTTP, crawler tasks, browser, queue, DB, cache)
- Metrics exposed at `/metrics` endpoint
- Health check at `/health` with DB connection verification

### Data Flow Patterns

1. **Configuration Loading**: Settings loaded once via `get_settings()` LRU cache
2. **Database Access**:
   - Use `Depends(get_db)` for SQLAlchemy sessions (legacy patterns)
   - Use repository classes with `AsyncConnection` for sqlc queries (preferred)
   - All queries return type-safe Pydantic models
3. **Logging**: Get logger with `get_logger(__name__)`, logs structured JSON
4. **Storage**: Base64-encoded GCS credentials decoded and used to create service account
5. **Caching**: Redis async client for URL deduplication and rate limiting

### Key Design Decisions

- **Async everywhere**: FastAPI + SQLAlchemy async + Redis async + httpx
- **Type-safe database**: sqlc generates Python code from SQL queries
- **Dependency injection**: FastAPI's `Depends()` for DB sessions and services
- **Configuration**: Environment-based with Pydantic validation
- **Observability first**: Structured logging + Prometheus metrics from the start
- **Service-oriented**: Business logic in service classes, routes stay thin

## Important Patterns

### Adding a New API Endpoint

**Important**: All API models must be imported from `crawler.api.generated`, not from any other location.

1. Define schema in `openapi.yaml` first (contract-first approach)
2. Run `make generate-models` to generate Pydantic models
3. Define route in `crawler/api/v1/routes/*.py` or `crawler/api/routes.py`
4. Import models: `from crawler.api.generated import YourRequestModel, YourResponseModel`
5. Use repository classes for database access (see "Working with Database" below)
6. Add metrics tracking if needed (import from `crawler.core.metrics`)
7. Use structured logging: `logger.info("event_name", key=value)`

**Import Examples**:
```python
# ✅ CORRECT: Import from crawler.api.generated
from crawler.api.generated import CreateWebsiteRequest, WebsiteResponse

# ❌ INCORRECT: Don't import from models.py directly
from crawler.api.generated.models import CreateWebsiteRequest

# ✅ CORRECT: For common schemas (non-OpenAPI models)
from crawler.api.schemas import ErrorResponse, HealthResponse
```

### Adding a New Service
1. Create service class in `crawler/services/`
2. Initialize in `__init__` with settings from `get_settings()`
3. Use async methods throughout
4. Add structured logging for key operations
5. Add relevant Prometheus metrics

### Working with Database

**Adding New Queries**:
1. Write SQL query in `sql/queries/*.sql` following sqlc syntax
2. Run `sqlc generate` to generate Python code
3. Import generated queries in `crawler/db/repositories.py`
4. Add repository method wrapping the generated query
5. Use repository in your routes/services

**Schema Changes**:
1. Add new table or modify schema in `sql/schema/*.sql` (single source of truth)
2. Create new SQL migration file in `sql/schema/` with next version number
3. Add sqlc queries in `sql/queries/*.sql` for the new table
4. Run `sqlc generate` to generate type-safe Python models and queries
5. Add repository methods in `crawler/db/repositories.py` if needed
6. Update tests to verify new functionality

**Note**: SQL schema files are the only place to define database structure. No Python table definitions needed - sqlc generates Pydantic models directly from SQL queries.

**Using Repositories**:
```python
from crawler.db import get_db
from crawler.db.repositories import WebsiteRepository

async with get_db() as session:
    async with session.begin():
        repo = WebsiteRepository(session.connection())
        website = await repo.create(
            name="example",
            base_url="https://example.com",
            config={}
        )
        # Returns Pydantic model with type safety
        print(website.id, website.name)
```

### Working with Scheduled Jobs

**Creating a Scheduled Job**:
```python
from datetime import datetime, UTC
from crawler.db.repositories import ScheduledJobRepository

async with get_db() as session:
    async with session.begin():
        scheduled_job_repo = ScheduledJobRepository(session.connection())

        # Create a scheduled job with bi-weekly schedule
        job = await scheduled_job_repo.create(
            website_id=website.id,
            cron_schedule="0 0 1,15 * *",  # 1st and 15th at midnight
            next_run_time=datetime.now(UTC),
            is_active=True,
            job_config={"max_depth": 5}
        )
```

**Finding Jobs Due for Execution**:
```python
# Get all jobs that need to run
due_jobs = await scheduled_job_repo.get_due_jobs(
    cutoff_time=datetime.now(UTC),
    limit=100
)

for job in due_jobs:
    # Process the job
    # Update next_run_time after execution
    await scheduled_job_repo.update_next_run(
        job_id=job.id,
        next_run_time=calculate_next_run(job.cron_schedule),
        last_run_time=datetime.now(UTC)
    )
```

**Pausing/Resuming Schedules**:
```python
# Pause a schedule without deleting it
await scheduled_job_repo.toggle_status(job_id=job.id, is_active=False)

# Resume the schedule
await scheduled_job_repo.toggle_status(job_id=job.id, is_active=True)
```

**Notes**:
- Default cron schedule for websites: `0 0 1,15 * *` (bi-weekly)
- Use `is_active=False` to pause schedules instead of deleting
- Composite index on `(is_active, next_run_time)` optimizes job lookup
- `job_config` JSONB field allows per-job configuration overrides

### Contract-First API Development

This project uses **OpenAPI spec as the single source of truth** for API contracts. The workflow ensures frontend and backend stay in sync.

**Architecture** (Data Flow):
```
1. openapi.yaml (Contract - single source of truth)
       ↓
2. make generate-models (datamodel-codegen)
       ↓
3. crawler/api/generated/models.py (auto-generated, git-ignored)
       ↓
4. crawler/api/generated/extended.py (extends models with validators)
       ↓
5. crawler/api/generated/__init__.py (re-exports extended models)
       ↓
6. Your code: from crawler.api.generated import YourModel
       ↓
7. FastAPI routes use models
       ↓
8. Contract tests verify implementation matches openapi.yaml
```

**Key Architectural Points**:
- 📄 **Single source of truth**: `openapi.yaml` defines all API contracts
- 🤖 **Auto-generation**: `models.py` is never edited manually
- ✨ **Extension layer**: `extended.py` adds custom validation without touching generated code
- 📦 **Clean imports**: Always `from crawler.api.generated import ...`
- ✅ **Validation**: Contract tests ensure spec and implementation stay in sync

**Workflow for API Changes**:

1. **Update Contract**: Edit `openapi.yaml` with new endpoints/schemas
   ```bash
   # Edit openapi.yaml to add/modify endpoints
   make validate-openapi  # Validate spec is correct
   ```

2. **Generate Models**: Run code generation (creates `models.py` - don't edit this file!)
   ```bash
   make generate-models  # Auto-generates crawler/api/generated/models.py
   # ⚠️ models.py is git-ignored and regenerated every time!
   ```

3. **Add Custom Validators** (ONLY if your new model needs custom validation):
   - **manually edit** `crawler/api/generated/extended.py` (this file is version controlled)
   - Import the base model from `models.py` and extend it
   ```python
   # In crawler/api/generated/extended.py
   from .models import YourNewModel as _YourNewModel

   class YourNewModel(_YourNewModel):
       """Extended model with custom validators."""

       @model_validator(mode="after")
       def your_custom_validation(self) -> "YourNewModel":
           # Custom validation logic
           return self
   ```
   - Export it in `crawler/api/generated/__init__.py`

4. **Implement Routes**: Use models in FastAPI (import directly from `crawler.api.generated`)
   ```python
   from crawler.api.generated import CreateWebsiteRequest, WebsiteResponse
   # Imports from crawler.api.generated.__init__.py which re-exports extended models

   @router.post("", response_model=WebsiteResponse, operation_id="createWebsite")
   async def create_website(request: CreateWebsiteRequest) -> WebsiteResponse:
       # Implementation uses type-safe models with custom validators
       pass
   ```

5. **Run Contract Tests**: Verify implementation matches spec
   ```bash
   uv run pytest tests/integration/test_openapi_contract.py -v
   ```

6. **Generate Client SDK** (optional, for frontend/external consumers):
   ```bash
   make generate-client  # Creates clients/python/ SDK
   ```

**Key Points**:
- ❌ **NEVER edit** `crawler/api/generated/models.py` - it's regenerated every time
- ✅ **DO edit** `crawler/api/generated/extended.py` - this is manually maintained
- ✅ **DO commit** `extended.py` and `__init__.py` to git
- ❌ **DON'T commit** `models.py` - it's in .gitignore
- 🤖 **CI automatically** generates `models.py` before running tests

**Contract Tests** (`tests/integration/test_openapi_contract.py`):
- ✅ API version and title match
- ✅ All contract paths implemented
- ✅ No undocumented paths
- ✅ HTTP methods consistency
- ✅ Operation IDs match
- ✅ Response schemas defined
- ✅ Tags consistency
- ✅ Required components present
- ✅ Documentation completeness

**Benefits**:
1. **Single source of truth** - OpenAPI spec defines everything
2. **Type safety** - Auto-generated Pydantic models ensure correctness
3. **Contract validation** - Tests prevent drift between spec and implementation
4. **Client generation** - Automatic SDK for any language (Python, TypeScript, Go, etc.)
5. **Team collaboration** - Frontend/backend agree on API before implementation

**File Ownership & Version Control**:

```
crawler/api/generated/
├── models.py          ❌ AUTO-GENERATED (git-ignored)
│                      └─ NEVER EDIT - regenerated by make generate-models
│                      └─ CI generates this before tests
│
├── extended.py        ✅ MANUALLY MAINTAINED (version controlled)
│                      └─ Edit this to add custom validators
│                      └─ Imports from models.py and extends classes
│                      └─ Commit this file
│
└── __init__.py        ✅ MANUALLY MAINTAINED (version controlled)
                       └─ Edit this to export your extended models
                       └─ Commit this file
```

**Common Mistakes to Avoid**:

- ❌ **DON'T** create `crawler/api/v1/schemas/` directory
  - This was removed to avoid duplicate sources of truth
  - All OpenAPI models come from `crawler.api.generated`

- ❌ **DON'T** create manual Pydantic models that duplicate OpenAPI schemas
  - Define schemas in `openapi.yaml` instead
  - Run `make generate-models` to get type-safe models

- ❌ **DON'T** import from `models.py` directly

  ```python
  from crawler.api.generated.models import CreateWebsiteRequest  # ❌ WRONG
  ```

- ✅ **DO** import from `crawler.api.generated` (the `__init__.py`)

  ```python
  from crawler.api.generated import CreateWebsiteRequest  # ✅ CORRECT
  ```

- ❌ **DON'T** edit `models.py` to add validators
  - It will be overwritten on next generation
  - Add validators in `extended.py` instead

- ✅ **DO** extend generated models in `extended.py`

  ```python
  # In extended.py
  from .models import YourModel as _YourModel

  class YourModel(_YourModel):
      @model_validator(mode="after")
      def your_validator(self) -> "YourModel":
          # Custom logic here
          return self
  ```

**Other Important Files**:
- `openapi.yaml` - API contract (✅ version controlled, source of truth)
- `clients/python/` - Generated SDK (❌ git-ignored, regenerated)
- `docs/openapi-generation.md` - Detailed documentation

### Testing
- Unit tests go in `tests/unit/`
- Integration tests in `tests/integration/`
- **Contract tests** in `tests/integration/test_openapi_contract.py` (validates OpenAPI spec)
- Use `pytest-asyncio` for async tests (auto mode enabled in pyproject.toml)
- Test coverage reports generated to `htmlcov/`
- Database tests use repository fixtures: `website_repo`, `crawl_job_repo`, `scheduled_job_repo`, etc.
- Fixtures automatically create schema from SQL files and clean up after tests
- Schema cleanup is automatic - queries PostgreSQL system tables to drop all tables and types
- No manual maintenance needed when adding new tables or types

**Test Categories**:
1. **Unit Tests** - Business logic, validators, utilities
2. **Integration Tests** - Database repositories, API endpoints, Redis cache
3. **Contract Tests** - OpenAPI spec vs FastAPI implementation validation

## Technology Stack Notes

**Package Manager**: This project uses [uv](https://github.com/astral-sh/uv) for fast dependency management. All Python commands should be run via `uv run` or within the uv environment.

**Type-Safe Queries**: [sqlc](https://sqlc.dev) generates type-safe Python code from SQL. Run `sqlc generate` after modifying queries in `sql/queries/*.sql`. Generated code is in `crawler/db/generated/` (never edit manually).

**Browser Automation**: Playwright browsers must be installed separately with `make playwright`. For anti-bot scenarios, undetected-chromedriver is available.

**Message Queue**: NATS JetStream is configured but crawler worker implementation is not yet complete.

**Monitoring Stack**: Full observability with Prometheus (metrics), Grafana (dashboards), Loki (log aggregation), and AlertManager. Access via `make monitoring-up` and `make urls`.

## Environment Configuration

Key environment variables (see `.env.example`):
- `DATABASE_URL`: PostgreSQL async connection string (postgresql+asyncpg://...)
- `REDIS_URL`: Redis connection URL
- `NATS_URL`: NATS server URL
- `GCS_BUCKET_NAME`: GCS bucket for HTML storage
- `GOOGLE_APPLICATION_CREDENTIALS_BASE64`: Base64-encoded service account JSON
- `MAX_CONCURRENT_REQUESTS`: Concurrency limit for crawler
- `LOG_LEVEL`: DEBUG/INFO/WARNING/ERROR
- `ENVIRONMENT`: development/staging/production

Use `make encode-gcs FILE=path/to/creds.json` to generate base64-encoded GCS credentials.

## Code Style

- **Linting**: ruff with line length 100
- **Type hints**: Required (mypy with `disallow_untyped_defs = true`)
- **Imports**: Auto-sorted by ruff (E, F, I, N, W, UP rules enabled)
- **Python version**: 3.11+ required
- **Async functions**: Use `async def` with proper typing (collections.abc.AsyncGenerator, etc.)

## CI/CD

### GitHub Actions Workflows

**CI Pipeline** (`.github/workflows/ci.yml`) - Optimized for minimal runner usage
- Runs only on PRs to `main` (not on push to avoid duplicate runs)
- Path filtering: only runs when relevant files change (`.py`, `pyproject.toml`, `openapi.yaml`, Docker files)
- Single Python version (3.11) instead of matrix to save runner time
- Spins up PostgreSQL and Redis services automatically
- **Auto-generates OpenAPI models** before running tests (models are not committed to git)
- Executes: **OpenAPI contract validation** → format check → lint → type-check (non-blocking) → **generate models** → tests
- **Contract tests** automatically run as part of integration test suite
- Fast-fail tests (`--maxfail=3`) to stop early on failures
- Quiet output (`-q`) to reduce log size
- No coverage uploads to save bandwidth
- Aggressive caching for uv dependencies

**Important**: `crawler/api/generated/models.py` is auto-generated during CI and NOT committed to git. The CI automatically runs `datamodel-codegen` from `openapi.yaml` before tests.

**Claude Code Review** (`.github/workflows/claude-code-review.yml`)
- Automatically reviews PRs using Claude Code
- Provides feedback on code quality, bugs, performance, security, and test coverage
- Uses repository's CLAUDE.md for style guidance
- Posts review as PR comment

**Claude Interaction** (`.github/workflows/claude.yml`)
- Triggered by `@claude` mentions in issues or PR comments
- Allows Claude to interact with issues and PRs
- Can read CI results to provide context-aware assistance

### Dependabot Configuration

**Automatic Dependency Updates** (`.github/dependabot.yml`) - Optimized for low noise
- Runs monthly on first Monday at 09:00 (reduced from weekly to minimize CI runs)
- Limited concurrent PRs: 5 for Python, 3 for Actions/Docker
- Grouped updates for related packages:
  - `fastapi`: FastAPI ecosystem (fastapi, pydantic, uvicorn, starlette)
  - `database`: SQLAlchemy, asyncpg, alembic
  - `browser`: Playwright, Selenium, undetected-chromedriver
  - `cloud`: Google Cloud, Redis
  - `monitoring`: Prometheus, structlog
  - `testing`: pytest packages
  - `dev-tools`: ruff, mypy
- Also updates GitHub Actions and Docker images
- Commit message prefixes: `deps:`, `ci:`, `docker:`

### Cost Optimization Notes

The CI/CD setup is optimized to minimize GitHub Actions usage:
- **Single Python version**: Only 3.11 instead of matrix builds (saves ~50% runner time)
- **Path filtering**: CI only runs when code/config files change (skips docs/markdown-only changes)
- **No push triggers**: Only runs on PR creation/updates, not on main branch pushes
- **Fast-fail tests**: Stops after 3 failures to avoid wasting time
- **Monthly dependencies**: Dependabot runs monthly instead of weekly
- **Grouped updates**: Multiple related packages updated in single PRs
- **Limited concurrency**: Max 5 Python PRs, 3 Actions/Docker PRs at once
- **No coverage uploads**: Saves bandwidth and external service dependencies

### Pre-merge Checklist

Before merging a PR, ensure:
1. All CI checks pass (OpenAPI validation, format, lint, type-check, tests)
2. **Contract tests pass** (if API changes made)
3. Claude Code Review feedback addressed (if applicable)
4. No merge conflicts with `main`

**For API Changes Specifically**:
1. ✅ Updated `openapi.yaml` with new endpoints/schemas
2. ✅ Ran `make validate-openapi` - spec is valid
3. ✅ Ran `make generate-models` locally (to test generation works)
4. ✅ If new models need custom validation: **manually updated** `crawler/api/generated/extended.py`
5. ✅ Updated `crawler/api/generated/__init__.py` exports if added new models
6. ✅ **Committed** `openapi.yaml`, `extended.py`, `__init__.py` (NOT `models.py`!)
7. ✅ Ran contract tests: `uv run pytest tests/integration/test_openapi_contract.py -v` - all pass
8. ✅ All 14+ contract tests pass

**What Gets Committed**:
- ✅ `openapi.yaml` - the contract
- ✅ `crawler/api/generated/extended.py` - your custom validators
- ✅ `crawler/api/generated/__init__.py` - exports
- ❌ `crawler/api/generated/models.py` - NEVER commit (git-ignored, CI generates it)
