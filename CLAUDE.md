# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Communication Style: Be direct and straightforward. No cheerleading phrases like "that's absolutely right" or "great question." Tell me when my ideas are flawed, incomplete, or poorly thought through. Use casual language and occasional profanity when appropriate. Focus on practical problems and realistic solutions rather than being overly positive or encouraging.

Technical Approach: Challenge assumptions, point out potential issues, and ask the hard questions about implementation, scalability, and real-world viability. If something won't work, say so directly and explain why it has problems rather than just dismissing it.

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
- API routes defined in `crawler/api/routes.py` (base routes)
- API v1 routes in modular structure under `crawler/api/v1/`
- CORS middleware enabled for all origins

**Configuration** (`config/settings.py`)
- Pydantic Settings-based configuration
- All settings loaded from environment variables or `.env` file
- Cached with `@lru_cache` decorator (`get_settings()`)
- Environment-aware: development/staging/production

**Centralized Dependency Injection** (`crawler/core/dependencies.py`)
- **Single source of truth** for all dependency injection across the application
- **Core dependencies**: Settings, Database sessions, Redis clients
- **Service factories**: Create service instances with proper dependency injection
- **Type aliases**: `SettingsDep`, `DBSessionDep`, `RedisDep`, `CacheServiceDep`, etc.
- **Consistent patterns**: All dependencies follow the same injection pattern
- **Reusable**: API v1 dependencies build on top of core dependencies

**Modular API v1 Architecture** (`crawler/api/v1/`)
- **Clear separation of concerns** with layered architecture:
  - `routes/` - FastAPI route definitions (thin, endpoint registration only)
  - `handlers/` - HTTP request handlers (coordinate routes and services)
  - `services/` - Business logic services (domain rules, no HTTP concerns)
  - `dependencies.py` - API v1-specific DI (builds on core dependencies)
  - `decorators.py` - Reusable decorators for consistent error handling
- **Benefits**:
  - **Testability**: Each layer can be tested independently
  - **Maintainability**: Changes isolated to appropriate layers
  - **Scalability**: Easy to add new endpoints following the same pattern
  - **Type Safety**: Full type hints and dependency injection throughout

**Error Handling Decorator** (`crawler/api/v1/decorators.py`)
- **`@handle_service_errors(operation="...")`**: Centralized exception handling for all API handlers
- **Exception Mapping**:
  - `ValueError` → 400 Bad Request (business validation errors like "not found", "already exists")
  - `RuntimeError` → 500 Internal Server Error (service operation failures)
  - `Exception` → 500 Internal Server Error (unexpected errors)
  - `HTTPException` → Re-raised as-is (already handled by handler pre-validation)
- **Features**:
  - Consistent structured logging with handler name and error context
  - Full exception chaining for debugging (`from e`)
  - Configurable error messages via `operation` parameter
  - Type-safe with `ParamSpec` and `TypeVar` for async functions
- **Usage**: Apply to all handler functions to ensure consistent error handling
- **Benefits**: DRY principle, single place for error handling changes, consistent API error responses

**Database Layer** (`crawler/db/`)
- **SQL schema as single source of truth**: `sql/schema/*.sql` defines all tables and types
- **sqlc** generates type-safe Python code from SQL queries
- **Modular repository pattern**: Each entity has its own repository file
- SQLAlchemy 2.0 for connections and sessions only (asyncpg driver)
- Async session factory in `session.py`, connection pooling via settings
- SQL queries in `sql/queries/*.sql`, schema in `sql/schema/*.sql`
- Generated code in `crawler/db/generated/` (never edit manually)
- **Repository structure**:
  - `repositories/base.py` - Shared utilities for all repositories
  - `repositories/website.py` - Website-specific operations
  - `repositories/crawl_job.py` - Crawl job operations
  - `repositories/scheduled_job.py` - Scheduled job operations
  - `repositories/crawled_page.py` - Crawled page operations
  - `repositories/content_hash.py` - Content hash operations
  - `repositories/crawl_log.py` - Crawl log operations
- Each repository handles JSON serialization and parameter mapping
- **Core tables**: `website`, `crawl_job`, `crawled_page`, `content_hash`, `crawl_log`, `scheduled_job`
- **Scheduled jobs**: Websites can have default cron schedules; `scheduled_job` table tracks recurring crawls with `is_active` flag for pausing

**Services** (`crawler/services/`)
- `CacheService`: Redis-based caching for URL deduplication and rate limiting
- `StorageService`: GCS for raw HTML storage with base64-encoded credentials
- `URLDeduplicationCache`: Deduplicate URLs to avoid re-crawling
- `RateLimiter`: Redis-based rate limiting for crawl requests
- `JobProgressCache`: Track crawl job progress in Redis
- `BrowserPoolStatus`: Monitor browser pool status
- `JobCancellationFlag`: Manage job cancellation signals
- All services use async/await patterns
- All services injected via centralized dependency system

**Observability** (`crawler/core/`)
- `logging.py`: structlog for structured JSON logging
- `metrics.py`: Prometheus metrics (HTTP, crawler tasks, browser, queue, DB, cache)
- `dependencies.py`: Centralized dependency injection system
- Metrics exposed at `/metrics` endpoint
- Health check at `/health` with DB connection verification

### Data Flow Patterns

1. **Configuration Loading**: Settings loaded once via `get_settings()` LRU cache
2. **Dependency Injection Flow**:
   - Import type aliases from `crawler.core.dependencies` (e.g., `DBSessionDep`, `RedisDep`)
   - FastAPI automatically injects dependencies based on type annotations
   - Services receive their dependencies through constructors
   - Repositories receive database connections from services
3. **Database Access**:
   - Use centralized `DBSessionDep` from `crawler.core.dependencies`
   - Repository classes use `AsyncConnection` for sqlc queries
   - All queries return type-safe Pydantic models
   - Transactions managed automatically by session context
4. **Logging**: Get logger with `get_logger(__name__)`, logs structured JSON
5. **Storage**: Base64-encoded GCS credentials decoded and used to create service account
6. **Caching**: Redis services injected via centralized dependencies

### Modular Architecture Pattern (API v1)

The application follows a **layered architecture** with clear separation of concerns:

```
HTTP Request
    ↓
[Route Layer] (crawler/api/v1/routes/*.py)
    - Registers FastAPI endpoints
    - Defines OpenAPI documentation
    - Specifies response models
    - MINIMAL logic (just routing)
    ↓
[Handler Layer] (crawler/api/v1/handlers/*.py)
    - Validates HTTP requests
    - Coordinates service calls
    - Translates exceptions to HTTP responses
    - Handles HTTP-specific concerns
    ↓
[Service Layer] (crawler/api/v1/services/*.py)
    - Implements business logic
    - Enforces domain rules
    - Manages transactions
    - NO HTTP awareness
    ↓
[Repository Layer] (crawler/db/repositories/*.py)
    - Database operations only
    - Type-safe sqlc-generated queries
    - JSON serialization
    - Parameter mapping
    ↓
Database
```

**Key Principles**:

1. **Single Responsibility**: Each layer has one clear purpose
2. **Dependency Direction**: Dependencies flow downward (routes → handlers → services → repositories)
3. **Testing**: Each layer can be tested independently with mocked dependencies
4. **Reusability**: Services can be used by multiple handlers; repositories by multiple services
5. **Type Safety**: Full type hints throughout all layers

### Key Design Decisions

- **Async everywhere**: FastAPI + SQLAlchemy async + Redis async + httpx
- **Type-safe database**: sqlc generates Python code from SQL queries
- **Dependency injection**: FastAPI's `Depends()` for DB sessions and services
- **Configuration**: Environment-based with Pydantic validation
- **Observability first**: Structured logging + Prometheus metrics from the start
- **Service-oriented**: Business logic in service classes, routes stay thin

## Important Patterns

### Adding a New API Endpoint

**Important**: Follow the modular layered architecture. All API models must be imported from `crawler.api.generated`.

#### Step-by-Step Guide:

**1. Define API Contract** (`openapi.yaml`)
```yaml
# Define request/response schemas in openapi.yaml
paths:
  /api/v1/resources:
    post:
      summary: Create a resource
      operationId: createResource
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateResourceRequest'
```

**2. Generate Models**
```bash
make generate-models  # Generates Pydantic models from OpenAPI spec
```

**3. Create Route** (`crawler/api/v1/routes/resources.py`)
```python
from fastapi import APIRouter, status
from crawler.api.generated import CreateResourceRequest, ResourceResponse
from crawler.api.v1.dependencies import ResourceServiceDep
from crawler.api.v1.handlers import create_resource_handler

router = APIRouter()

@router.post("", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def create_resource(
    request: CreateResourceRequest,
    resource_service: ResourceServiceDep,
) -> ResourceResponse:
    """Create a new resource."""
    return await create_resource_handler(request, resource_service)
```

**4. Create Handler** (`crawler/api/v1/handlers/resources.py`)
```python
from crawler.api.generated import CreateResourceRequest, ResourceResponse
from crawler.api.v1.decorators import handle_service_errors

@handle_service_errors(operation="creating the resource")  # ValueError→400, RuntimeError→500
async def create_resource_handler(
    request: CreateResourceRequest,
    resource_service: ResourceService,
) -> ResourceResponse:
    logger.info("create_resource_request", resource_name=request.name)
    return await resource_service.create_resource(request)
```

**5. Create Service** (`crawler/api/v1/services/resources.py`)
```python
class ResourceService:
    def __init__(self, resource_repo: ResourceRepository):
        self.resource_repo = resource_repo

    async def create_resource(self, request: CreateResourceRequest) -> ResourceResponse:
        # Business logic validation
        if await self.resource_repo.get_by_name(request.name):
            raise ValueError(f"Resource '{request.name}' already exists")

        resource = await self.resource_repo.create(name=request.name, ...)
        return ResourceResponse.model_validate(resource)
```

**6. Add Dependency Provider** (`crawler/api/v1/dependencies.py`)
```python
from typing import Annotated
from fastapi import Depends
from crawler.api.v1.services import ResourceService
from crawler.core.dependencies import DBSessionDep
from crawler.db.repositories import ResourceRepository

async def get_resource_service(db: DBSessionDep) -> ResourceService:
    """Get resource service with injected dependencies."""
    conn = await db.connection()
    resource_repo = ResourceRepository(conn)
    return ResourceService(resource_repo=resource_repo)

ResourceServiceDep = Annotated[ResourceService, Depends(get_resource_service)]
```

**7. Create Repository** (if needed - see "Working with Database" below)

**8. Register Router** (`crawler/api/v1/router.py`)
```python
from crawler.api.v1.routes import resources

api_v1_router.include_router(resources.router, prefix="/resources", tags=["Resources"])
```

**Import Pattern**: Always `from crawler.api.generated import ...` (see Contract-First section for details)

**Layer Responsibilities**: Routes (registration) → Handlers (HTTP) → Services (business logic) → Repositories (DB)

### Adding a New Service
1. Create service class in `crawler/services/`
2. Initialize in `__init__` with settings from `get_settings()`
3. Use async methods throughout
4. Add structured logging for key operations
5. Add relevant Prometheus metrics

### Working with Database

The project uses a **modular repository pattern** with each entity having its own repository file in `crawler/db/repositories/`.

**Repository Structure**:
```
crawler/db/repositories/
├── __init__.py          # Exports all repositories
├── base.py              # Shared utilities (to_uuid, etc.)
├── website.py           # WebsiteRepository
├── crawl_job.py         # CrawlJobRepository
├── scheduled_job.py     # ScheduledJobRepository
├── crawled_page.py      # CrawledPageRepository
├── content_hash.py      # ContentHashRepository
└── crawl_log.py         # CrawlLogRepository
```

**Adding a New Repository**:

1. **Write SQL queries** in `sql/queries/your_entity.sql`:
```sql
-- name: CreateYourEntity :one
INSERT INTO your_entity (name, config) VALUES ($1, $2) RETURNING *;

-- name: GetYourEntityByID :one
SELECT * FROM your_entity WHERE id = $1;
```

2. **Generate type-safe code**:
```bash
make sqlc-generate  # or: sqlc generate
```

3. **Create repository file** `crawler/db/repositories/your_entity.py`:
```python
from sqlalchemy.ext.asyncio import AsyncConnection
from crawler.db.generated import queries
from crawler.db.generated.models import YourEntity
from crawler.db.repositories.base import to_uuid

class YourEntityRepository:
    """Repository for your_entity table operations."""

    def __init__(self, conn: AsyncConnection):
        self.conn = conn

    async def create(self, name: str, config: dict) -> YourEntity:
        """Create a new entity."""
        return await queries.create_your_entity(
            self.conn, name=name, config=config
        )

    async def get_by_id(self, entity_id: str) -> YourEntity | None:
        """Get entity by ID."""
        return await queries.get_your_entity_by_id(
            self.conn, id=to_uuid(entity_id)
        )
```

4. **Export from `__init__.py`**:
```python
from crawler.db.repositories.your_entity import YourEntityRepository

__all__ = ["YourEntityRepository", ...]
```

5. **Use in services** via dependency injection (see "Adding a New API Endpoint")

**Schema Changes with Alembic**:

The project uses **Alembic** for database migrations. All schema changes must go through Alembic:

1. **Create new migration**: `make db-migrate-create MSG="add user authentication table"`
   - This creates a new migration file in `alembic/versions/`
   - The file will have empty `upgrade()` and `downgrade()` functions

2. **Edit migration file**: Add SQL to `upgrade()` and `downgrade()` functions:
   ```python
   def upgrade() -> None:
       op.execute("""
       CREATE TABLE user_auth (
           id UUID PRIMARY KEY DEFAULT uuidv7(),
           username VARCHAR(255) NOT NULL UNIQUE,
           ...
       );
       CREATE INDEX ix_user_auth_username ON user_auth(username);
       """)

   def downgrade() -> None:
       op.execute("DROP TABLE IF EXISTS user_auth CASCADE;")
   ```

3. **Apply migration**: `make db-migrate` (runs `alembic upgrade head`)
   - Test locally first
   - In production, migrations run automatically via `scripts/run_migrations.py`

4. **Regenerate schema**: `make regenerate-schema`
   - Dumps current database state to `sql/schema/current_schema.sql`
   - This is used by sqlc for code generation (not for migrations!)

5. **Add sqlc queries**: Write queries in `sql/queries/*.sql`

6. **Generate code**: `make sqlc-generate`
   - Creates type-safe Python code from queries
   - Generates Pydantic models

7. **Create repository**: Add repository file in `crawler/db/repositories/`

8. **Export repository**: Update `crawler/db/repositories/__init__.py`

9. **Test**: Verify migration works:
   ```bash
   make db-migrate-rollback  # Test downgrade
   make db-migrate           # Test upgrade
   make test-integration     # Run tests
   ```

**Important Notes**:
- **Never edit `sql/schema/current_schema.sql` manually** - it's auto-generated
- **All schema changes go through Alembic migrations** in `alembic/versions/`
- **sql/migrations/*.sql are historical** - kept for reference, not used
- **Use raw SQL in migrations** - Alembic `op.execute()` for full PostgreSQL features
- **No SQLAlchemy ORM** - we use sqlc for type-safe queries instead

**Migration Commands**:
- `make db-migrate` - Apply pending migrations
- `make db-migrate-create MSG="description"` - Create new migration
- `make db-migrate-rollback` - Rollback last migration
- `make db-migrate-current` - Show current migration version
- `make db-migrate-history` - Show all migrations
- `make db-migrate-check` - Check if database is up to date

**Using Repositories**:
```python
# In services (recommended - via dependency injection)
class WebsiteService:
    def __init__(self, website_repo: WebsiteRepository):
        self.website_repo = website_repo

    async def create_website(self, name: str, base_url: str) -> Website:
        return await self.website_repo.create(name=name, base_url=base_url, config={})

# Direct usage (not recommended - use services instead)
async def my_function(db: DBSessionDep):
    conn = await db.connection()
    repo = WebsiteRepository(conn)
    website = await repo.create(name="example", base_url="https://example.com", config={})
```

### Working with Scheduled Jobs

```python
# Create scheduled job (bi-weekly: 1st & 15th at midnight)
job = await scheduled_job_repo.create(
    website_id=website.id,
    cron_schedule="0 0 1,15 * *",
    next_run_time=datetime.now(UTC),
    is_active=True,
    job_config={"max_depth": 5}
)

# Get due jobs
due_jobs = await scheduled_job_repo.get_due_jobs(cutoff_time=datetime.now(UTC), limit=100)

# Update after execution
await scheduled_job_repo.update_next_run(job_id=job.id, next_run_time=next_time, last_run_time=datetime.now(UTC))

# Pause/resume
await scheduled_job_repo.toggle_status(job_id=job.id, is_active=False)
```

**Notes**: Default cron `0 0 1,15 * *` (bi-weekly). Use `is_active=False` to pause (don't delete). Composite index on `(is_active, next_run_time)` optimizes lookups. `job_config` JSONB allows per-job overrides.

### Contract-First API Development

**OpenAPI spec is the single source of truth** for all API contracts.

**Data Flow**: `openapi.yaml` → `make generate-models` → `models.py` (git-ignored) → `extended.py` (custom validators) → `__init__.py` (exports) → Your code → Contract tests

**Workflow**:
1. Edit `openapi.yaml` → `make validate-openapi`
2. `make generate-models` (generates `models.py` - DON'T edit this!)
3. Add custom validators in `extended.py` (if needed), export in `__init__.py`
4. Implement routes using models from `crawler.api.generated`
5. `uv run pytest tests/integration/test_openapi_contract.py -v`

**File Ownership**:
- `models.py` - ❌ Auto-generated, git-ignored, CI creates it, NEVER edit
- `extended.py` - ✅ Manually maintained, add custom validators here, commit to git
- `__init__.py` - ✅ Manually maintained, exports models, commit to git

**Import Pattern**:
```python
# ✅ CORRECT
from crawler.api.generated import CreateWebsiteRequest, WebsiteResponse

# ❌ WRONG - don't import from models.py directly
from crawler.api.generated.models import CreateWebsiteRequest
```

**Custom Validators** (in `extended.py`):
```python
from .models import YourModel as _YourModel

class YourModel(_YourModel):
    @model_validator(mode="after")
    def your_validator(self) -> "YourModel":
        # Custom logic
        return self
```

**Contract Tests**: Verify API version, paths, methods, operation IDs, schemas, tags, documentation

**Benefits**: Single source of truth, type safety, prevents API drift, auto-generates SDKs

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

**Message Queue**: NATS JetStream is fully integrated for distributed job queuing with immediate cancellation support. See `docs/NATS_INTEGRATION.md` for details.

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

## Coding Patterns

### Guard Pattern and Early Returns

Use guard clauses and early returns to reduce nesting and improve code readability. Check for invalid/edge cases first and return/exit early.

**Pattern**: Check preconditions at the start of a function and return early if they're not met.

**Benefits**:
- Reduces nesting levels (avoid deep if-else pyramids)
- Makes happy path code more prominent
- Easier to understand control flow
- Clearer error handling

**Examples**:

```python
# ❌ BAD: Nested conditions
async def process_item(config, item_id):
    if config.enabled:
        if item_id:
            if await check_permission(item_id):
                # Main logic buried 3 levels deep
                return await process(item_id)
            else:
                return None
        else:
            return None
    else:
        return None

# ✅ GOOD: Guard pattern with early returns
async def process_item(config, item_id):
    # Guard: feature not enabled
    if not config.enabled:
        return None

    # Guard: missing item_id
    if not item_id:
        return None

    # Guard: insufficient permissions
    if not await check_permission(item_id):
        return None

    # Main logic at top level - clear and prominent
    return await process(item_id)
```

**Real example** (`crawler/services/seed_url_crawler.py:133-184`):
```python
async def _check_cancellation(self, config, seed_url, pages_crawled, extracted_urls, warnings=None):
    """Uses guard pattern to exit early when cancellation not configured or not triggered."""
    # Guard: no cancellation flag configured
    if not config.cancellation_flag:
        return None

    # Guard: no job_id to check
    if not config.job_id:
        return None

    # Guard: job not cancelled
    if not await config.cancellation_flag.is_cancelled(config.job_id):
        return None

    # Main logic - job is cancelled
    logger.info("crawl_cancelled", job_id=config.job_id, pages_crawled=pages_crawled)
    return CrawlResult(outcome=CrawlOutcome.CANCELLED, seed_url=seed_url, ...)
```

**Use for**: Preconditions, validation, optional features, permissions. **Avoid when**: Else branch has substantial logic, cleanup needed, or both branches equally important. **Comment guards**: `# Guard: <condition>`

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

**Standard**:
1. All CI checks pass (OpenAPI validation, format, lint, type-check, tests)
2. Claude Code Review feedback addressed (if applicable)
3. No merge conflicts with `main`

**For API Changes**: See "Contract-First API Development" section. Summary: Update `openapi.yaml` → `make validate-openapi` → `make generate-models` → Add validators in `extended.py` (if needed) → Run contract tests → Commit `openapi.yaml`, `extended.py`, `__init__.py` (NOT `models.py`)
