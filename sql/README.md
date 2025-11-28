# SQL Directory - Single Source of Truth

**This directory is the single source of truth for:**
1. ✅ Database schema (tables, indexes, constraints)
2. ✅ Database migrations (executed by `make db-migrate`)
3. ✅ sqlc code generation (type-safe Python code)

## Directory Structure

```
sql/
├── README.md                        # This file
├── schema/                          # Schema files = Migrations
│   ├── 000_migration_tracking.sql   # Migration tracking table
│   └── 001_initial_schema.sql       # Initial schema (version 001)
└── queries/                         # SQL queries for sqlc
    ├── website.sql
    ├── crawl_job.sql
    ├── crawled_page.sql
    ├── content_hash.sql
    └── crawl_log.sql
```

## Key Principle

**No duplication!** Schema files in `sql/schema/` ARE the migrations.

- 📝 Write schema once in `sql/schema/`
- 🚀 Run `make db-migrate` to apply
- 🔧 Run `make sqlc-generate` to regenerate code
- ✅ Done!

## Workflow

### 1. Create New Schema File

Create a new numbered file in `sql/schema/`:

```bash
vim sql/schema/002_add_analytics.sql
```

Add metadata at the top:

```sql
-- version: 002
-- description: Add analytics tables
-- requires: PostgreSQL 18+
-- date: 2025-10-27

CREATE TABLE analytics_events (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    event_type VARCHAR(100) NOT NULL,
    data JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

### 2. Apply Migration

```bash
make db-migrate
```

This executes the schema file and tracks it in `schema_migrations`.

### 3. Generate Code

```bash
make sqlc-generate
```

This regenerates Python code from the updated schema.

### 4. Add Queries (Optional)

Add corresponding queries in `sql/queries/`:

```bash
vim sql/queries/analytics.sql
```

```sql
-- name: CreateAnalyticsEvent :one
INSERT INTO analytics_events (event_type, data)
VALUES ($1, $2)
RETURNING *;

-- name: ListAnalyticsEvents :many
SELECT * FROM analytics_events
WHERE event_type = $1
ORDER BY created_at DESC
LIMIT $2;
```

Then run `make sqlc-generate` again.

## Schema File Format

### Required Metadata

Each schema file must have metadata at the top:

```sql
-- version: 001
-- description: Brief description of what this migration does
-- requires: PostgreSQL 18+
-- date: YYYY-MM-DD
```

### Versioning

- **000**: Reserved for infrastructure (migration tracking table)
- **001-999**: Feature migrations
- Use zero-padded numbers: `001`, `002`, `003`

### File Naming

Pattern: `{version}_{description}.sql`

Examples:
- `001_initial_schema.sql`
- `002_add_analytics.sql`
- `003_add_user_tracking.sql`

## Migration Tracking

Migrations are tracked in the `schema_migrations` table:

| Column | Type | Description |
|--------|------|-------------|
| version | VARCHAR(255) | Migration version (e.g., "001") |
| applied_at | TIMESTAMPTZ | When migration was applied |
| description | TEXT | Human-readable description |
| checksum | VARCHAR(64) | SHA256 hash for integrity |

### Checksum Detection

The migration runner calculates SHA256 checksums:
- ✅ **New file**: Applies migration
- ⚠️  **Checksum changed**: Warns but allows (development only!)
- ✓ **Checksum matches**: Skips (already applied)

## Query Files

Located in `sql/queries/`, organized by entity:

```
sql/queries/
├── website.sql         # Website CRUD operations
├── crawl_job.sql       # Job management
├── crawled_page.sql    # Page operations
├── content_hash.sql    # Hash tracking
└── crawl_log.sql       # Logging operations
```

### Query Annotations

sqlc uses special comments:

| Annotation | Meaning | Python Return Type |
|------------|---------|-------------------|
| `:one` | Single row | `Model \| None` |
| `:many` | Multiple rows | `AsyncIterator[Model]` |
| `:exec` | No return | `None` |

Example:

```sql
-- name: GetWebsiteByID :one
SELECT * FROM website WHERE id = $1;

-- name: ListWebsites :many
SELECT * FROM website
WHERE status = COALESCE($1, status)
ORDER BY created_at DESC
LIMIT $2 OFFSET $3;

-- name: DeleteWebsite :exec
DELETE FROM website WHERE id = $1;
```

## Commands

| Command | Purpose |
|---------|---------|
| `make db-migrate` | Apply pending schema files as migrations |
| `make db-migrate-status` | Show migration status with checksums |
| `make db-migrate-down` | Drop all tables and rollback |
| `make sqlc-generate` | Generate Python code from schema + queries |

## PostgreSQL 18+ Features

### UUIDv7

Time-ordered UUIDs (built-in, no extension):

```sql
CREATE TABLE example (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    ...
);
```

Benefits:
- ⏰ Chronologically sortable
- 🚀 Better B-tree index performance
- 📊 No fragmentation

### Extensions

Enabled in `scripts/init-db.sql`:

```sql
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- Trigram similarity
CREATE EXTENSION IF NOT EXISTS "btree_gin";   -- GIN indexes for btree
CREATE EXTENSION IF NOT EXISTS "pg_search";   -- Full-text search
```

### JSONB

Flexible JSON with indexing:

```sql
config JSONB NOT NULL DEFAULT '{}'::jsonb

-- GIN index for fast queries
CREATE INDEX idx_config ON website USING gin(config);
```

### Full-Text Search

```sql
-- Add tsvector column
ALTER TABLE crawled_page
ADD COLUMN search_vector tsvector
GENERATED ALWAYS AS (
    to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(extracted_content, ''))
) STORED;

-- GIN index for fast search
CREATE INDEX idx_page_search ON crawled_page USING gin(search_vector);
```

## Best Practices

### Schema Files

1. ✅ **One feature per file** - Keep migrations focused
2. ✅ **Include metadata** - Version, description, requirements
3. ✅ **Use descriptive names** - `002_add_user_tracking.sql`
4. ✅ **Never modify applied migrations** - Create new ones
5. ✅ **Test on clean database** - Ensure idempotency

### Query Files

1. ✅ **Descriptive query names** - `GetWebsiteByID`, not `Get1`
2. ✅ **Use RETURNING** - Get complete records after INSERT/UPDATE
3. ✅ **Use COALESCE** - Handle optional parameters
4. ✅ **Add comments** - Explain complex queries
5. ✅ **Group by entity** - One file per table/domain

### Development Workflow

1. 📝 Create schema file
2. 🧪 Test migration on local DB
3. 🔧 Generate code with sqlc
4. ✅ Verify generated code
5. 🚀 Commit schema + generated code together

## Examples

### Adding a New Table

**`sql/schema/002_add_user_sessions.sql`**:

```sql
-- version: 002
-- description: Add user session tracking
-- requires: PostgreSQL 18+
-- date: 2025-10-27

CREATE TABLE user_sessions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
    user_id VARCHAR(255) NOT NULL,
    session_token VARCHAR(255) NOT NULL UNIQUE,
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NOT NULL,
    last_activity_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_user_sessions_user_id ON user_sessions(user_id);
CREATE INDEX idx_user_sessions_token ON user_sessions(session_token);
CREATE INDEX idx_user_sessions_expires ON user_sessions(expires_at);
```

**`sql/queries/user_sessions.sql`**:

```sql
-- name: CreateUserSession :one
INSERT INTO user_sessions (user_id, session_token, ip_address, user_agent, expires_at)
VALUES ($1, $2, $3, $4, $5)
RETURNING *;

-- name: GetUserSession :one
SELECT * FROM user_sessions
WHERE session_token = $1 AND expires_at > CURRENT_TIMESTAMP;

-- name: DeleteExpiredSessions :exec
DELETE FROM user_sessions
WHERE expires_at < CURRENT_TIMESTAMP;
```

Then:

```bash
make db-migrate        # Apply schema
make sqlc-generate     # Generate code
```

### Modifying Existing Table

**`sql/schema/003_add_website_tags.sql`**:

```sql
-- version: 003
-- description: Add tags to websites
-- requires: PostgreSQL 18+
-- date: 2025-10-27

ALTER TABLE website
ADD COLUMN tags TEXT[] DEFAULT '{}';

CREATE INDEX idx_website_tags ON website USING gin(tags);
```

## Troubleshooting

### Migration fails with "relation already exists"

The migration was already applied. Check status:

```bash
make db-migrate-status
```

### Checksum mismatch warning

You modified an already-applied migration. In production, this should never happen.

**Development**: The migration re-applies (be careful!)
**Production**: Create a new migration instead

### sqlc generation fails

1. Check SQL syntax in schema files
2. Verify query annotations (`:one`, `:many`, `:exec`)
3. Ensure PostgreSQL 18+ compatibility

### Need to reset everything

```bash
make docker-down-v     # WARNING: Deletes all data!
make docker-up
make db-migrate
make sqlc-generate
```

## Further Reading

- [sqlc Documentation](https://docs.sqlc.dev/)
- [PostgreSQL 18 Release Notes](https://www.postgresql.org/docs/18/)
- [UUIDv7 Specification](https://datatracker.ietf.org/doc/html/draft-peabody-dispatch-new-uuid-format)
- [PostgreSQL Full-Text Search](https://www.postgresql.org/docs/18/textsearch.html)
