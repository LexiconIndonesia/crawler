# Lexicon Crawler

A scalable, production-ready web crawler built with FastAPI and modern Python async technologies.

## Features

- **Modern Async Architecture**: Built on FastAPI and async/await patterns
- **Browser Automation**: Playwright for JavaScript-heavy sites, undetected-chromedriver for anti-bot bypass
- **Distributed Queue**: NATS JetStream for reliable task distribution
- **Scheduled Crawls**: Cron-based scheduling with pause/resume capability and bi-weekly defaults
- **Persistent Storage**: PostgreSQL for structured data, Google Cloud Storage for raw HTML
- **Type-Safe Queries**: sqlc for compile-time safe SQL queries with Pydantic models
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
make test             # Run all tests
make test-cov         # Run tests with coverage

# Code Quality
make format           # Format code with ruff
make lint             # Check code with linter
make type-check       # Run type checking
make check            # Run all quality checks

# Docker
make docker-up        # Start all services
make docker-down      # Stop all services
make docker-logs      # View service logs
make docker-status    # Show service status

# Database
make db-up            # Start database services
make db-shell         # Connect to PostgreSQL
make redis-shell      # Connect to Redis

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
├── monitoring/           # Monitoring configurations
│   ├── prometheus/       # Prometheus config and alerts
│   ├── grafana/         # Grafana dashboards
│   ├── loki/            # Loki log aggregation
│   └── alertmanager/    # Alert management
├── scripts/             # Utility scripts
├── docs/                # Documentation
├── main.py              # Application entry point
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

### Running Tests

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run unit tests only
make test-unit

# Run integration tests only
make test-integration

# Run tests in watch mode
make test-watch
```

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

- **API Documentation**: http://localhost:8000/docs
- **API Alternative Docs**: http://localhost:8000/redoc
- **Health Check**: http://localhost:8000/health
- **Prometheus Metrics**: http://localhost:8000/metrics
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

## License

[Your License Here]

## Support

For issues and questions:
- GitHub Issues: [Repository Issues]
- Documentation: [Link to docs]
