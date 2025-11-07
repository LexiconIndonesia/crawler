# Database Migrations

This directory contains numbered migration files that track the evolution of the database schema over time.

## Migration Files

Migrations are applied in numerical order:

- `000_migration_tracking.sql` - Migration tracking table
- `001_initial_schema.sql` - Core tables (website, crawl_job, crawled_page, content_hash, crawl_log)
- `002_scheduled_jobs.sql` - Scheduled crawling support
- `003_seed_url_submissions.sql` - Seed URL submission tracking
- `004_partition_crawl_log.sql` - Partition management for crawl_log table

## Important Notes

- **Do not modify existing migrations** - they represent historical database changes
- **Do not delete migrations** - the database relies on these for its current state
- **These files are NOT used by sqlc** - they contain runtime-specific code (PL/pgSQL functions, system catalog queries) that sqlc cannot parse
- For sqlc code generation, see `sql/schema/` which contains the static schema definition

## Applying Migrations

Migrations are applied manually or via deployment scripts in numerical order.

### Manual Application

```bash
# Connect to database
make db-shell

# Apply specific migration
\i sql/migrations/001_initial_schema.sql
```

### Production Deployment

In production, migrations should be applied via Alembic (see Phase 3 of schema migration plan).

## Creating New Migrations

When making schema changes:

1. Create a new numbered file (e.g., `005_your_change.sql`)
2. Include both DDL and any necessary data migrations
3. Test on a development database first
4. After applying, regenerate static schema: `make regenerate-schema`
5. Regenerate sqlc code: `make sqlc-generate`

## Schema vs Migrations

- **`sql/migrations/`** - Historical evolution of the database (this directory)
- **`sql/schema/`** - Current static schema definition (used by sqlc)

The schema directory is regenerated from the database after migrations are applied.
