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
- SQLAlchemy 2.0 with async support (asyncpg driver)
- Async session factory created at module level in `session.py`
- `get_db()` dependency provides sessions with automatic commit/rollback
- Connection pooling configured via settings (pool_size, max_overflow)

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
2. **Database Sessions**: Use `Depends(get_db)` for automatic session lifecycle
3. **Logging**: Get logger with `get_logger(__name__)`, logs structured JSON
4. **Storage**: Base64-encoded GCS credentials decoded and used to create service account
5. **Caching**: Redis async client for URL deduplication and rate limiting

### Key Design Decisions

- **Async everywhere**: FastAPI + SQLAlchemy async + Redis async + httpx
- **Dependency injection**: FastAPI's `Depends()` for DB sessions and services
- **Configuration**: Environment-based with Pydantic validation
- **Observability first**: Structured logging + Prometheus metrics from the start
- **Service-oriented**: Business logic in service classes, routes stay thin

## Important Patterns

### Adding a New API Endpoint
1. Define route in `crawler/api/routes.py`
2. Use `Depends(get_db)` for database access
3. Add metrics tracking if needed (import from `crawler.core.metrics`)
4. Use structured logging: `logger.info("event_name", key=value)`

### Adding a New Service
1. Create service class in `crawler/services/`
2. Initialize in `__init__` with settings from `get_settings()`
3. Use async methods throughout
4. Add structured logging for key operations
5. Add relevant Prometheus metrics

### Database Models
- Use SQLAlchemy 2.0 declarative syntax
- Place in `crawler/models/`
- Create corresponding Pydantic schemas in `crawler/schemas/`
- Run migrations with Alembic (not yet configured in current setup)

### Testing
- Unit tests go in `tests/unit/`
- Integration tests in `tests/integration/`
- Use `pytest-asyncio` for async tests (auto mode enabled in pyproject.toml)
- Test coverage reports generated to `htmlcov/`

## Technology Stack Notes

**Package Manager**: This project uses [uv](https://github.com/astral-sh/uv) for fast dependency management. All Python commands should be run via `uv run` or within the uv environment.

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
