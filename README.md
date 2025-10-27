# Lexicon Crawler

A scalable, production-ready web crawler built with FastAPI and modern Python async technologies.

## 🚀 Current Development: API Scheduling & Contract Testing

**Branch**: `feature/implements-api-scheduling` | **Version**: 1.0.0

### New in This Branch

✅ **Website Management API** - Create and configure websites with multi-step crawl/scrape workflows
✅ **Scheduled Crawling** - Cron-based recurring crawls with pause/resume capability
✅ **OpenAPI Contract Testing** - Automated validation ensuring API spec and implementation stay in sync
✅ **Contract-First Development** - OpenAPI spec as single source of truth for API contracts
✅ **Type-Safe Code Generation** - Auto-generate Pydantic models from OpenAPI spec

**Try it now:**
```bash
# Create a website with scheduled crawling
curl -X POST http://localhost:8000/api/v1/websites \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Example Site",
    "base_url": "https://example.com",
    "schedule": {
      "type": "recurring",
      "cron": "0 0 1,15 * *",
      "enabled": true
    },
    "steps": [
      {
        "name": "crawl_list",
        "type": "crawl",
        "method": "http",
        "config": {"url": "https://example.com/articles"},
        "selectors": {"detail_urls": ".article-link"}
      }
    ]
  }'
```

## Features

- **RESTful API v1**: Full-featured API for website management and crawl configuration
- **Contract-First Development**: OpenAPI 3.1 spec with automated contract testing
- **Modern Async Architecture**: Built on FastAPI and async/await patterns
- **Browser Automation**: Playwright for JavaScript-heavy sites, undetected-chromedriver for anti-bot bypass
- **Distributed Queue**: NATS JetStream for reliable task distribution
- **Scheduled Crawls**: Cron-based scheduling with pause/resume capability and bi-weekly defaults
- **Multi-Step Workflows**: Define complex crawl/scrape pipelines with data flow between steps
- **Persistent Storage**: PostgreSQL for structured data, Google Cloud Storage for raw HTML
- **Type-Safe Queries**: sqlc for compile-time safe SQL queries with Pydantic models
- **Type-Safe APIs**: Auto-generated Pydantic models from OpenAPI spec
- **High-Performance Parsing**: selectolax for fast HTML parsing
- **Caching & Deduplication**: Redis for URL deduplication and rate limiting
- **Full Observability**: Prometheus metrics, Grafana dashboards, Loki log aggregation
- **Production Ready**: Docker containerization, health checks, graceful shutdown

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Language | Python 3.11+ |
| Web Framework | FastAPI |
| Browser Automation | Playwright, undetected-chromedriver |
| HTTP Client | httpx |
| HTML Parsing | selectolax, BeautifulSoup4 |
| Message Queue | NATS JetStream |
| Database | PostgreSQL + sqlc |
| ORM/Query Builder | SQLAlchemy 2.0 + sqlc |
| Cache | Redis |
| Object Storage | Google Cloud Storage |
| Monitoring | Prometheus + Grafana |
| Logging | Loki |
| Alerting | AlertManager |

## Prerequisites

- Python 3.11 or higher
- [UV](https://github.com/astral-sh/uv) package manager
- Docker and Docker Compose (for running services)
- Google Cloud credentials (for GCS storage)
- [sqlc](https://sqlc.dev) for generating type-safe queries (optional, only if modifying SQL)

## Quick Start

### 1. Install UV

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone and Setup

```bash
git clone <repository-url>
cd crawler
```

### 3. Complete Setup

```bash
# One-command setup (installs dependencies + Playwright + creates .env)
make setup

# Or manually:
make install-dev    # Install dependencies
make playwright     # Install Playwright browsers
cp .env.example .env  # Create environment file
```

### 4. Start Development

```bash
# Start database services + development server
make dev
```

That's it! The API is now running at http://localhost:8000

### Alternative: Start All Services

```bash
# Start everything (app + databases + monitoring)
make docker-up

# View all service URLs
make urls
```

## Available Commands

View all available commands:
```bash
make help
```

### Common Commands

```bash
# Development
make dev              # Start dev server with auto-reload
make run              # Run production server
make test             # Run all tests (including contract tests)
make test-cov         # Run tests with coverage

# OpenAPI & Code Generation
make validate-openapi # Validate OpenAPI specification
make generate-models  # Generate Pydantic models from OpenAPI
make generate-client  # Generate Python client SDK
make generate-all     # Validate + generate all OpenAPI artifacts

# Code Quality
make format           # Format code with ruff
make lint             # Check code with linter
make type-check       # Run type checking
make check            # Run all quality checks
make pre-commit       # Run format + lint-fix + type-check

# Docker
make docker-up        # Start all services
make docker-down      # Stop all services
make docker-logs      # View service logs
make docker-status    # Show service status

# Database
make db-up            # Start database services
make db-shell         # Connect to PostgreSQL
make redis-shell      # Connect to Redis
make sqlc-generate    # Generate type-safe queries from SQL

# Monitoring
make monitoring-up    # Start monitoring stack
make urls             # Show all service URLs

# Utilities
make clean            # Clean temporary files
make info             # Show project information
```

## Development

### Project Structure

```
crawler/
├── crawler/                # Main application package
│   ├── api/               # API routes and endpoints
│   │   ├── generated/    # ⚠️ OpenAPI-generated models (single source of truth)
│   │   │   ├── models.py      # ❌ AUTO-GENERATED - never edit (git-ignored)
│   │   │   ├── extended.py    # ✅ Custom validators (version controlled)
│   │   │   └── __init__.py    # ✅ Re-exports extended models (version controlled)
│   │   ├── v1/           # API version 1
│   │   │   ├── routes/   # V1 endpoint implementations
│   │   │   ├── services/ # V1 business logic
│   │   │   └── handlers/ # V1 request handlers
│   │   ├── schemas/      # Common schemas (HealthResponse, ErrorResponse)
│   │   └── routes.py     # Base routes (health, metrics)
│   ├── core/              # Core functionality (logging, metrics)
│   ├── db/                # Database layer
│   │   ├── generated/    # sqlc-generated queries (do not edit)
│   │   ├── repositories.py  # Repository pattern for DB access
│   │   └── session.py    # Database session management
│   ├── models/            # Domain models
│   ├── schemas/           # Pydantic schemas (domain models, not DB models)
│   ├── services/          # Business logic services
│   └── utils/             # Utility functions
├── sql/                   # SQL queries and schema
│   ├── queries/          # sqlc query definitions
│   └── schema/           # Database schema SQL
├── config/                # Configuration management
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   └── integration/      # Integration tests
│       └── test_openapi_contract.py  # Contract tests
├── monitoring/           # Monitoring configurations
│   ├── prometheus/       # Prometheus config and alerts
│   ├── grafana/         # Grafana dashboards
│   ├── loki/            # Loki log aggregation
│   └── alertmanager/    # Alert management
├── clients/              # Generated client SDKs (not version controlled)
│   └── python/          # Auto-generated Python client
├── scripts/             # Utility scripts
├── docs/                # Documentation
│   └── openapi-generation.md  # OpenAPI workflow guide
├── main.py              # Application entry point
├── openapi.yaml         # OpenAPI 3.1 API contract (single source of truth)
├── pyproject.toml       # Project dependencies
├── sqlc.yaml            # sqlc configuration
└── docker-compose.yml   # Service orchestration
```

### Working with Database

This project uses **sqlc** for type-safe database queries. SQL schema files are the **single source of truth**:

**Schema Management:**
1. **Define schema** in `sql/schema/*.sql` (tables, indexes, types)
2. **Write queries** in `sql/queries/*.sql` (with sqlc annotations)
3. **Run `sqlc generate`** to generate type-safe Python code
4. **Use repositories** in `crawler/db/repositories.py`

**Key Points:**
- No Python table definitions needed - sqlc generates Pydantic models from SQL
- All database structure defined in SQL files only
- Generated code in `crawler/db/generated/` (never edit manually)
- Tests automatically create and clean up schema from SQL files

**Example Usage:**
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

**Scheduled Jobs:**

Websites support recurring crawls via cron schedules:
- Default schedule: `0 0 1,15 * *` (bi-weekly on 1st and 15th at midnight)
- Use `ScheduledJobRepository` to manage scheduled crawls
- Pause/resume schedules with `is_active` flag (preserves history)
- Optimized indexes for finding jobs due for execution

See `docs/SQLC_IMPLEMENTATION.md` for detailed guide.

### Working with the API (Contract-First Development)

This project uses **OpenAPI spec as the single source of truth** for API contracts. This ensures frontend and backend stay perfectly in sync.

**Quick Workflow:**

1. **Define API in OpenAPI spec** (`openapi.yaml`)
2. **Validate spec**: `make validate-openapi`
3. **Generate models**: `make generate-models`
4. **Implement routes** using generated Pydantic models
5. **Run contract tests**: Tests automatically verify implementation matches spec

**Example: Adding a New Endpoint**

1. **Edit** `openapi.yaml`:
```yaml
paths:
  /api/v1/crawl-jobs:
    post:
      summary: Create a new crawl job
      operationId: createCrawlJob
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/CreateCrawlJobRequest'
```

2. **Generate models** (creates `models.py` - don't edit it!):
```bash
make generate-models  # Creates crawler/api/generated/models.py
# ⚠️ models.py is git-ignored, regenerated every time
```

3. **Add custom validators** (ONLY if needed) in `extended.py`:
```python
# In crawler/api/generated/extended.py (manually maintained)
from .models import CreateCrawlJobRequest as _CreateCrawlJobRequest

class CreateCrawlJobRequest(_CreateCrawlJobRequest):
    """Extended with custom validation."""

    @model_validator(mode="after")
    def validate_job_config(self) -> "CreateCrawlJobRequest":
        # Custom validation logic
        return self
```

4. **Implement in FastAPI** (import directly from `crawler.api.generated`):
```python
# ✅ CORRECT: Import directly from crawler.api.generated
from crawler.api.generated import CreateCrawlJobRequest, CrawlJobResponse

@router.post("", response_model=CrawlJobResponse, operation_id="createCrawlJob")
async def create_crawl_job(request: CreateCrawlJobRequest) -> CrawlJobResponse:
    # Implementation uses type-safe models with custom validators
    pass
```

**Import Pattern**:
- ✅ **Always import from**: `from crawler.api.generated import YourModel`
- ❌ **Never import from**: `models.py` directly (use the `__init__.py` re-exports)
- 📦 **What you get**: Extended models with custom validators, not raw generated models

5. **Verify with contract tests**:
```bash
uv run pytest tests/integration/test_openapi_contract.py -v
```

**Remember**:
- ❌ NEVER edit `models.py` (it's regenerated)
- ✅ DO edit `extended.py` (manually maintained)
- ❌ DON'T commit `models.py` (git-ignored)
- ✅ DO commit `openapi.yaml`, `extended.py`, `__init__.py`

**Contract Tests Verify:**
- ✅ All paths in `openapi.yaml` are implemented
- ✅ No undocumented endpoints exist
- ✅ Response schemas match
- ✅ Operation IDs match
- ✅ HTTP methods match
- ✅ API version and title match

**File Management:**
- `crawler/api/generated/models.py` - **Auto-generated, never edit** (git-ignored, CI generates it)
- `crawler/api/generated/extended.py` - **Manually maintained** (version controlled)
- `crawler/api/generated/__init__.py` - **Manually maintained exports** (version controlled)
- `clients/python/` - **Auto-generated SDK** (git-ignored)

See `docs/openapi-generation.md` for the complete guide.

### Running Tests

```bash
# Run all tests (unit + integration + contract tests)
make test

# Run with coverage
make test-cov

# Run unit tests only
make test-unit

# Run integration tests only (includes contract tests)
make test-integration

# Run contract tests only
uv run pytest tests/integration/test_openapi_contract.py -v

# Run tests in watch mode
make test-watch
```

**Test Coverage:**
- **179 total tests** (as of v1.0.0)
- Unit tests: Business logic, validators, utilities
- Integration tests: API endpoints, database, Redis, scheduled jobs
- **Contract tests** (14 tests): Validate OpenAPI spec vs FastAPI implementation

### Code Quality

```bash
# Format code
make format

# Lint code
make lint

# Lint with auto-fix
make lint-fix

# Type checking
make type-check

# Run all checks (format + lint + type-check)
make check
```

## Accessing Services

View all service URLs:
```bash
make urls
```

Once running, you can access:

**API Endpoints:**
- **Swagger UI**: http://localhost:8000/docs (interactive API documentation)
- **ReDoc**: http://localhost:8000/redoc (alternative API docs)
- **OpenAPI Spec**: http://localhost:8000/openapi.json (JSON spec)
- **Health Check**: http://localhost:8000/health
- **Prometheus Metrics**: http://localhost:8000/metrics

**API v1 Endpoints:**
- **Create Website**: POST http://localhost:8000/api/v1/websites

**Monitoring:**
- **Grafana Dashboard**: http://localhost:3000 (admin/admin)
- **Prometheus UI**: http://localhost:9090
- **AlertManager**: http://localhost:9093
- **NATS Monitoring**: http://localhost:8222

## Monitoring

### Prometheus Metrics

The application exposes various metrics:

- HTTP request metrics (count, duration, status)
- Crawler task metrics (total, completed, failed)
- Browser session metrics
- Database connection pool metrics
- Cache hit/miss rates
- Queue message metrics

### Grafana Dashboards

Access Grafana at http://localhost:3000 to view:

- Application performance metrics
- Crawler throughput and success rates
- Infrastructure health
- Error rates and alerts

### Logs

Logs are aggregated in Loki and can be viewed in Grafana:

- Structured JSON logging
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL
- Searchable by service, level, and custom fields

## Configuration

Configuration is managed through environment variables. See `.env.example` for all available options.

### Setting up GCS Credentials

To encode your GCS service account credentials:

```bash
make encode-gcs FILE=path/to/service-account.json
```

Copy the output and add it to your `.env` file as `GOOGLE_APPLICATION_CREDENTIALS_BASE64`.

### Key Configurations

- `DATABASE_URL`: PostgreSQL connection string
- `REDIS_URL`: Redis connection string
- `NATS_URL`: NATS server URL
- `GCS_BUCKET_NAME`: Google Cloud Storage bucket
- `GOOGLE_APPLICATION_CREDENTIALS_BASE64`: Base64-encoded GCS credentials
- `MAX_CONCURRENT_REQUESTS`: Concurrent request limit
- `LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)

## Docker Deployment

### Build and Run

```bash
# Build the image
make docker-build

# Start all services
make docker-up

# View logs
make docker-logs

# Check service status
make docker-status

# Stop all services
make docker-down

# Stop and remove volumes
make docker-down-v
```

### Production Deployment

For production deployment:

1. Set `ENVIRONMENT=production` in `.env`
2. Configure proper database credentials
3. Set up GCS credentials
4. Configure AlertManager for notifications
5. Use proper secrets management
6. Set up reverse proxy (nginx/traefik)
7. Enable SSL/TLS

## Troubleshooting

### Common Issues

**Playwright Installation Issues**
```bash
# Install Playwright browsers
make playwright

# Or install system dependencies manually
uv run playwright install-deps chromium
```

**Database Connection Errors**
```bash
# Check PostgreSQL is running
make docker-status

# Connect to database shell
make db-shell
```

**Redis Connection Issues**
```bash
# Check service status
make docker-status

# Connect to Redis shell
make redis-shell
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and code quality checks:
   ```bash
   make check    # Run all checks
   make test     # Run tests
   ```
5. Submit a pull request

## Documentation

- [Database Schema](docs/DATABASE_SCHEMA.md) - Database design and Redis caching
- [sqlc Implementation](docs/SQLC_IMPLEMENTATION.md) - Type-safe SQL queries guide
- [OpenAPI Code Generation](docs/openapi-generation.md) - Contract-first API development guide
- [API Documentation](http://localhost:8000/docs) - Interactive Swagger UI (when running)
- [API Alternative Docs](http://localhost:8000/redoc) - ReDoc interface (when running)

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [Repository Issues]
- Documentation: [Link to docs]
