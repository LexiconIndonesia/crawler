# Database Schema (Static Definition)

This directory contains the **current state** of the database schema, used for sqlc code generation.

## ⚠️ Auto-Generated - Do Not Edit Manually

The file `current_schema.sql` is **auto-generated** from the database and should **not be edited manually**.

## Purpose

This static schema file is used by sqlc to:
- Generate type-safe Python query code
- Create Pydantic models for database tables
- Provide IDE autocompletion for queries

## Regenerating Schema

After applying new migrations, regenerate this schema:

```bash
make regenerate-schema
```

Or manually:

```bash
# Dump current schema from database
pg_dump --schema-only --no-owner --no-privileges \
    postgresql://user:pass@host:5432/dbname \
    > sql/schema/current_schema.sql

# Clean up (remove SET commands, public. prefixes, partition management functions)
# Then regenerate sqlc code
make sqlc-generate
```

## What's Excluded

The schema file **excludes** runtime-specific code that sqlc cannot parse:

- PostgreSQL system catalog queries (`pg_tables`, `pg_class`, etc.)
- Partition management views (`crawl_log_partitions`)
- Dynamic partition creation functions
- Session-specific SET commands

These features are in `sql/migrations/` and are applied at runtime, not during code generation.

## Schema vs Migrations

- **`sql/schema/`** - Current static schema (this directory, used by sqlc)
- **`sql/migrations/`** - Historical evolution of schema (applied to database)

Think of it this way:
- **Migrations** = Git commits (history of changes)
- **Schema** = Current HEAD (latest state)

## sqlc Configuration

The schema is referenced in `sqlc.yaml`:

```yaml
sql:
  - schema: "sql/schema"  # Points to this directory
    queries: "sql/queries"
    engine: "postgresql"
```

## Workflow

1. Create new migration in `sql/migrations/`
2. Apply migration to database
3. Regenerate schema: `make regenerate-schema`
4. Regenerate sqlc code: `make sqlc-generate`
5. Commit both migration and updated schema

## See Also

- `sql/migrations/README.md` - Migration file documentation
- `docs/TODO_SCHEMA_MIGRATION_REFACTOR.md` - Complete migration refactor plan
