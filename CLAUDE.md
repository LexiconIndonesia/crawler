# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Lexicon Crawler is a production-ready web crawler built with FastAPI and modern Python async patterns. It combines browser automation (Playwright, undetected-chromedriver) with distributed task queuing (NATS JetStream), persistent storage (PostgreSQL + GCS), and full observability (Prometheus, Grafana, Loki).

## Development Commands

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
1. Define route in `crawler/api/routes.py`
2. Use repository classes for database access (see "Working with Database" below)
3. Add metrics tracking if needed (import from `crawler.core.metrics`)
4. Use structured logging: `logger.info("event_name", key=value)`

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

### Testing
- Unit tests go in `tests/unit/`
- Integration tests in `tests/integration/`
- Use `pytest-asyncio` for async tests (auto mode enabled in pyproject.toml)
- Test coverage reports generated to `htmlcov/`
- Database tests use repository fixtures: `website_repo`, `crawl_job_repo`, `scheduled_job_repo`, etc.
- Fixtures automatically create schema from SQL files and clean up after tests
- Schema cleanup is automatic - queries PostgreSQL system tables to drop all tables and types
- No manual maintenance needed when adding new tables or types

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
- Path filtering: only runs when relevant files change (`.py`, `pyproject.toml`, Docker files)
- Single Python version (3.11) instead of matrix to save runner time
- Spins up PostgreSQL and Redis services automatically
- Executes: format check → lint → type-check (non-blocking) → tests
- Fast-fail tests (`--maxfail=3`) to stop early on failures
- Quiet output (`-q`) to reduce log size
- No coverage uploads to save bandwidth
- Aggressive caching for uv dependencies

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
1. All CI checks pass (format, lint, type-check, tests)
2. Claude Code Review feedback addressed (if applicable)
3. No merge conflicts with `main`
