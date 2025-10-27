# Database Schema Documentation

## Overview

The Lexicon Crawler uses **PostgreSQL** for persistent storage and **Redis** for caching and ephemeral state management. The database layer uses **sqlc** for type-safe SQL queries with **SQLAlchemy** for connections only. SQL schema files are the single source of truth.

## Architecture

- **PostgreSQL**: Primary data storage for websites, jobs, pages, and logs
- **Redis**: Caching layer for URL deduplication, rate limiting, job cancellation flags, browser pool status, and job progress
- **SQL Schema Files**: Single source of truth for database structure in `sql/schema/*.sql`
- **sqlc**: Generates type-safe Python code and Pydantic models from SQL queries
- **SQLAlchemy 2.0**: Connection pooling and sessions only (no table definitions)
- **Repository Pattern**: Clean interfaces in `crawler/db/repositories.py` wrapping sqlc-generated queries
- **asyncpg**: Async PostgreSQL driver
- **redis.asyncio**: Async Redis client

## Database Schema

### Schema Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              POSTGRESQL TABLES                              │
└─────────────────────────────────────────────────────────────────────────────┘

┌──────────────────────┐
│      WEBSITE         │
├──────────────────────┤
│ id (UUID) PK         │
│ name (VARCHAR) UQ    │
│ base_url (VARCHAR)   │
│ config (JSONB)       │◄────────┐
│ status (ENUM)        │         │
│ created_at (TSTZ)    │         │
│ updated_at (TSTZ)    │         │
│ created_by (VARCHAR) │         │
└──────────────────────┘         │
        │                        │
        │ 1:N                    │
        ▼                        │
┌──────────────────────┐         │
│     CRAWL_JOB        │         │
├──────────────────────┤         │
│ id (UUID) PK         │         │
│ website_id (UUID) FK ├─────────┘
│ job_type (ENUM)      │
│ seed_url (VARCHAR)   │
│ embedded_config      │
│   (JSONB)            │
│ status (ENUM)        │
│ priority (INT)       │
│ scheduled_at (TSTZ)  │
│ started_at (TSTZ)    │
│ completed_at (TSTZ)  │
│ cancelled_at (TSTZ)  │
│ cancelled_by (VAR)   │
│ cancellation_reason  │◄────────┐
│   (TEXT)             │         │
│ error_message (TEXT) │         │
│ retry_count (INT)    │         │
│ max_retries (INT)    │         │
│ metadata (JSONB)     │         │
│ variables (JSONB)    │         │
│ progress (JSONB)     │         │
│ created_at (TSTZ)    │         │
│ updated_at (TSTZ)    │         │
└──────────────────────┘         │
        │                        │
        │ 1:N                    │
        ▼                        │
┌──────────────────────┐         │
│   CRAWLED_PAGE       │         │
├──────────────────────┤         │
│ id (UUID) PK         │         │
│ website_id (UUID) FK ├─────────┤
│ job_id (UUID) FK     ├─────────┘
│ url (VARCHAR)        │
│ url_hash (VARCHAR)   │◄────────────┐
│   UQ(website_id+     │             │
│      url_hash)       │             │
│ content_hash (VAR)   ├──┐          │
│ title (VARCHAR)      │  │          │
│ extracted_content    │  │          │
│   (TEXT)             │  │          │
│ metadata (JSONB)     │  │          │
│ gcs_html_path (VAR)  │  │          │
│ gcs_documents        │  │          │
│   (JSONB)            │  │          │
│ is_duplicate (BOOL)  │  │          │
│ duplicate_of (UUID)  ├──┼──────────┘ (self-referential)
│   FK                 │  │
│ similarity_score     │  │
│   (INT)              │  │
│ crawled_at (TSTZ)    │  │
│ created_at (TSTZ)    │  │
└──────────────────────┘  │
                          │
        ┌─────────────────┘
        │ N:1
        ▼
┌──────────────────────┐
│   CONTENT_HASH       │
├──────────────────────┤
│ content_hash (VAR)   │
│   PK                 │
│ first_seen_page_id   │
│   (UUID) FK          │
│ occurrence_count     │
│   (INT)              │
│ last_seen_at (TSTZ)  │
│ created_at (TSTZ)    │
└──────────────────────┘


┌──────────────────────┐
│     CRAWL_LOG        │
├──────────────────────┤
│ id (BIGSERIAL) PK    │
│ job_id (UUID) FK     ├─────► CRAWL_JOB
│ website_id (UUID) FK ├─────► WEBSITE
│ step_name (VARCHAR)  │
│ log_level (ENUM)     │
│ message (TEXT)       │
│ context (JSONB)      │
│ trace_id (UUID)      │
│ created_at (TSTZ)    │
└──────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                              REDIS DATA STRUCTURES                          │
└─────────────────────────────────────────────────────────────────────────────┘

URL Deduplication:
  Key: url:dedup:{url_hash}
  Type: String (JSON)
  TTL: Configurable (default 3600s)
  Value: {"job_id": "...", "crawled_at": "..."}

Job Cancellation Flags:
  Key: job:cancel:{job_id}
  Type: String (JSON)
  TTL: 86400s (24 hours)
  Value: {"cancelled": true, "reason": "..."}

Rate Limiting:
  Key: ratelimit:{website_id}
  Type: Integer
  TTL: rate_limit_period (default 60s)
  Value: request_count

Browser Pool Status:
  Key: browser:pool:status
  Type: String (JSON)
  TTL: 300s (5 minutes)
  Value: {
    "active_browsers": N,
    "active_contexts": N,
    "available_contexts": N,
    "memory_mb": X.X
  }

Job Progress:
  Key: job:progress:{job_id}
  Type: String (JSON)
  TTL: 3600s (1 hour)
  Value: {
    "pages_crawled": N,
    "pages_pending": N,
    "errors": N,
    ...
  }
```

## Table Descriptions

### Website

Stores website configurations and metadata.

**Primary Key**: `id` (UUID)
**Unique Constraints**: `name`
**Foreign Keys**: None
**Indexes**:
- `ix_website_status` on `status`
- `ix_website_config` on `config` (GIN index for JSONB)
- `ix_website_created_at` on `created_at`

**Fields**:
- `id`: Unique identifier (auto-generated UUID)
- `name`: Unique website name (e.g., "docs-site")
- `base_url`: Base URL of the website
- `config`: JSONB configuration (max_depth, allowed_domains, etc.)
- `status`: active | inactive
- `created_at`: When website was added (TIMESTAMPTZ)
- `updated_at`: Last modification time (TIMESTAMPTZ)
- `created_by`: User who created the website

### Crawl_Job

Stores crawl job definitions and execution state.

**Primary Key**: `id` (UUID)
**Foreign Keys**:
- `website_id` → `website.id` (CASCADE)

**Indexes**:
- `ix_crawl_job_website_id` on `website_id`
- `ix_crawl_job_job_type` on `job_type`
- `ix_crawl_job_status` on `status`
- `ix_crawl_job_scheduled_at` on `scheduled_at`
- `ix_crawl_job_created_at` on `created_at`
- `ix_crawl_job_seed_url` on `seed_url`
- `ix_crawl_job_priority_status` on `(priority, status)` (composite, for job queue)

**Fields**:
- `id`: Unique job identifier
- `website_id`: Reference to website
- `job_type`: one_time | scheduled | recurring
- `seed_url`: Starting URL for crawl
- `embedded_config`: Job-specific configuration overrides (JSONB)
- `status`: pending | running | completed | failed | cancelled
- `priority`: 1-10 (higher = more important)
- `scheduled_at`: When job should run
- `started_at`: When job started
- `completed_at`: When job finished
- `cancelled_at`: When job was cancelled
- `cancelled_by`: User who cancelled
- `cancellation_reason`: Why job was cancelled
- `error_message`: Error details if failed
- `retry_count`: Current retry attempt
- `max_retries`: Maximum retry attempts
- `metadata`: Additional job metadata (JSONB)
- `variables`: Runtime variables (JSONB)
- `progress`: Job progress tracking (JSONB)

### Crawled_Page

Stores crawled page data and content.

**Primary Key**: `id` (UUID)
**Foreign Keys**:
- `website_id` → `website.id` (CASCADE)
- `job_id` → `crawl_job.id` (CASCADE)
- `duplicate_of` → `crawled_page.id` (SET NULL, self-referential)

**Unique Constraints**:
- `ix_crawled_page_website_url_hash` on `(website_id, url_hash)`

**Indexes**:
- `ix_crawled_page_website_id` on `website_id`
- `ix_crawled_page_job_id` on `job_id`
- `ix_crawled_page_url_hash` on `url_hash`
- `ix_crawled_page_content_hash` on `content_hash`
- `ix_crawled_page_crawled_at` on `crawled_at`
- `ix_crawled_page_is_duplicate` on `is_duplicate`
- `ix_crawled_page_duplicate_of` on `duplicate_of`

**Fields**:
- `id`: Unique page identifier
- `url`: Full page URL
- `url_hash`: SHA256 hash of URL (for deduplication)
- `content_hash`: SHA256 hash of content (for duplicate detection)
- `title`: Page title
- `extracted_content`: Extracted text content
- `metadata`: Page metadata (headers, status code, etc.) (JSONB)
- `gcs_html_path`: Path to raw HTML in GCS
- `gcs_documents`: Paths to extracted documents (JSONB)
- `is_duplicate`: Whether this page is a duplicate
- `duplicate_of`: Reference to original page if duplicate
- `similarity_score`: Content similarity (0-100)
- `crawled_at`: When page was crawled (TIMESTAMPTZ)

### Content_Hash

Tracks content hash occurrences for duplicate detection.

**Primary Key**: `content_hash` (VARCHAR)
**Foreign Keys**:
- `first_seen_page_id` → `crawled_page.id` (SET NULL)

**Indexes**:
- `ix_content_hash_last_seen_at` on `last_seen_at`
- `ix_content_hash_occurrence_count` on `occurrence_count`

**Fields**:
- `content_hash`: SHA256 content hash (primary key)
- `first_seen_page_id`: First page where content was seen
- `occurrence_count`: Number of times this content was encountered
- `last_seen_at`: Last time content was seen (TIMESTAMPTZ)
- `created_at`: First occurrence time (TIMESTAMPTZ)

### Crawl_Log

Stores detailed crawl execution logs.

**Primary Key**: `id` (BIGSERIAL)
**Foreign Keys**:
- `job_id` → `crawl_job.id` (CASCADE)
- `website_id` → `website.id` (CASCADE)

**Indexes**:
- `ix_crawl_log_job_id` on `job_id`
- `ix_crawl_log_website_id` on `website_id`
- `ix_crawl_log_log_level` on `log_level`
- `ix_crawl_log_created_at` on `created_at`
- `ix_crawl_log_trace_id` on `trace_id`
- `ix_crawl_log_job_created` on `(job_id, created_at)` (composite)

**Fields**:
- `id`: Auto-incrementing log ID
- `job_id`: Reference to crawl job
- `website_id`: Reference to website
- `step_name`: Crawler step/phase name
- `log_level`: DEBUG | INFO | WARNING | ERROR | CRITICAL
- `message`: Log message
- `context`: Additional context data (JSONB)
- `trace_id`: Distributed tracing UUID
- `created_at`: Log timestamp (TIMESTAMPTZ)

## Enums

### job_type_enum
- `one_time`: Single execution job
- `scheduled`: Run at a specific time
- `recurring`: Repeating job (cron-like)

### status_enum
Used by both `website` and `crawl_job`:
- `pending`: Not yet started
- `running`: Currently executing
- `completed`: Finished successfully
- `failed`: Finished with errors
- `cancelled`: Manually stopped
- `active`: Website is active (website only)
- `inactive`: Website is inactive (website only)

### log_level_enum
- `DEBUG`: Detailed debug information
- `INFO`: General informational messages
- `WARNING`: Warning messages
- `ERROR`: Error messages
- `CRITICAL`: Critical error messages

## Redis Data Structures

### URLDeduplicationCache

**Purpose**: Track which URLs have been crawled to avoid re-crawling
**Key Pattern**: `url:dedup:{url_hash}`
**Type**: String (JSON-serialized dict)
**TTL**: Configurable (default 3600s)
**Data**:
```json
{
  "job_id": "uuid",
  "crawled_at": "ISO8601 timestamp",
  "url": "original URL"
}
```

### JobCancellationFlag

**Purpose**: Fast in-memory flags for job cancellation
**Key Pattern**: `job:cancel:{job_id}`
**Type**: String (JSON-serialized dict)
**TTL**: 86400s (24 hours)
**Data**:
```json
{
  "cancelled": true,
  "reason": "Cancellation reason"
}
```

### RateLimiter

**Purpose**: Rate limit requests per website
**Key Pattern**: `ratelimit:{website_id}`
**Type**: Integer (request count)
**TTL**: `rate_limit_period` (default 60s)
**Value**: Current request count in window

### BrowserPoolStatus

**Purpose**: Track browser pool status for monitoring
**Key**: `browser:pool:status` (singleton)
**Type**: String (JSON-serialized dict)
**TTL**: 300s (5 minutes)
**Data**:
```json
{
  "active_browsers": 3,
  "active_contexts": 5,
  "available_contexts": 10,
  "memory_mb": 512.5
}
```

### JobProgressCache

**Purpose**: Cache job progress for fast reads
**Key Pattern**: `job:progress:{job_id}`
**Type**: String (JSON-serialized dict)
**TTL**: 3600s (1 hour)
**Data**:
```json
{
  "pages_crawled": 150,
  "pages_pending": 50,
  "errors": 2,
  "last_update": "ISO8601 timestamp"
}
```

## Schema Management

Database schema is defined in SQL files located in `sql/schema/`:

- `000_migration_tracking.sql`: Migration tracking table
- `001_initial_schema.sql`: All tables, indexes, constraints, and enums

**Key Principles:**
- SQL files are the **single source of truth** for database structure
- No Python table definitions needed - sqlc generates Pydantic models from SQL queries
- Tests automatically create and drop schema from SQL files
- Schema changes require adding new SQL migration files

Run migrations with:
```bash
# Apply all pending migrations
uv run python scripts/migrate.py up

# Rollback last migration
uv run python scripts/migrate.py down

# Check migration status
uv run python scripts/migrate.py status
```

## Repository Layer

Located in `crawler/db/repositories.py`, provides type-safe database access:

**WebsiteRepository**:
- `create(name, base_url, config, ...)` - Create new website
- `get_by_id(website_id)` - Get website by ID
- `get_by_name(name)` - Get website by name
- `list(status, limit, offset)` - List websites with pagination
- `count(status)` - Count websites
- `update(website_id, ...)` - Update website
- `delete(website_id)` - Delete website

**CrawlJobRepository**:
- `create(website_id, seed_url, ...)` - Create new job
- `get_by_id(job_id)` - Get job by ID
- `get_pending(limit)` - Get pending jobs ordered by priority
- `update_status(job_id, status, ...)` - Update job status
- `update_progress(job_id, progress)` - Update job progress
- `cancel(job_id, cancelled_by, reason)` - Cancel a job

**CrawledPageRepository**:
- `create(website_id, job_id, url, ...)` - Create crawled page record
- `get_by_id(page_id)` - Get page by ID
- `get_by_url_hash(website_id, url_hash)` - Get page by URL hash
- `list_by_job(job_id, limit, offset)` - List pages for a job
- `mark_as_duplicate(page_id, duplicate_of, similarity_score)` - Mark as duplicate

**ContentHashRepository**:
- `upsert(content_hash, first_seen_page_id)` - Insert or increment count
- `get(content_hash)` - Get content hash record

**CrawlLogRepository**:
- `create(job_id, website_id, message, ...)` - Create log entry
- `list_by_job(job_id, log_level, limit, offset)` - List logs for a job
- `get_errors(job_id, limit)` - Get error logs

All repositories return type-safe Pydantic models generated by sqlc from SQL queries in `sql/queries/*.sql`.

## Pydantic Models

**sqlc-Generated Models** (in `crawler/db/generated/models.py`):
- Automatically generated from SQL queries
- Type-safe representations of database rows
- Used by repository methods as return types
- Examples: `Website`, `CrawlJob`, `CrawledPage`, `ContentHash`, `CrawlLog`
- **Never edit manually** - regenerate with `sqlc generate`

**Domain Schemas** (in `crawler/schemas/`):
- Manually written for API request/response validation
- Examples: `WebsiteCreate`, `CrawlJobUpdate`, `CrawlLogFilter`
- Include validation rules and example data
- Used by FastAPI routes for request/response models

**Note:** sqlc models handle database operations, while domain schemas handle API validation. This separation keeps concerns clear.

## Testing

**Unit Tests**: `/tests/unit/test_schemas.py`
- Schema validation tests
- Field constraint tests
- Enum validation tests

**Integration Tests**:
- `/tests/integration/test_database.py` - Database operations via repositories
- `/tests/integration/test_repositories.py` - Repository pattern tests
- `/tests/integration/test_redis.py` - Redis operations

**Test Fixtures** (`tests/conftest.py`):
- Automatically create schema from `sql/schema/*.sql` files
- Automatic schema cleanup via PostgreSQL system table queries
- No manual maintenance when adding new tables or types
- Provides repository fixtures: `website_repo`, `crawl_job_repo`, etc.

Run tests with:
```bash
make test          # All tests
make test-unit     # Unit tests only
make test-integration  # Integration tests (requires DB)
```

## Connection Management

**PostgreSQL**:
- Engine created at module level in `crawler/db/session.py`
- Connection pooling configured via settings (pool_size, max_overflow)
- Async session factory with auto-commit/rollback
- Repository pattern uses `AsyncConnection` from sessions
- Use `Depends(get_db)` in FastAPI routes to get sessions
- Example: `repo = WebsiteRepository(session.connection())`

**Redis**:
- Each Redis service class creates its own client
- Support for shared client via constructor
- Always call `.close()` after use
- Connection retry handled automatically

## Health Checks

Health check endpoint at `/health` verifies:
- PostgreSQL connectivity (`SELECT 1`)
- Redis connectivity (`PING`)

Returns:
```json
{
  "status": "healthy",
  "timestamp": "2025-10-27T10:00:00Z",
  "checks": {
    "database": "connected",
    "redis": "connected"
  }
}
```
