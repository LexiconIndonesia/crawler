# Schema & Migration Refactor

**Status**: ✅ Complete
**Priority**: Medium
**Actual Time**: ~2 hours
**Completed**: 2025-11-07

---

## Problem Statement

Currently, `sql/schema/` contains both:
1. **Base schema definitions** (for sqlc code generation)
2. **Runtime migrations** (with DDL, PL/pgSQL functions, system catalog queries)

This causes sqlc generation to fail because it tries to parse migration files containing PostgreSQL system catalog references (`pg_class`, `pg_namespace`) that don't exist in sqlc's static analysis context.

**Current Error:**
```
sql/schema/004_partition_crawl_log.sql:1:1: relation "pg_tables" does not exist
sql/schema/004_partition_crawl_log.sql:1:1: relation "crawl_log_partitions" does not exist
```

---

## Solution Overview

Separate **static schema definitions** from **runtime migrations** following industry-standard patterns used by Django, Rails, Supabase, and other modern frameworks.

---

## Phase 1: Quick Fix (Immediate - 15 minutes)

### ✅ Objective
Unblock sqlc generation to enable `stream_logs_by_job()` method generation.

### Tasks

- [ ] **1.1: Update sqlc.yaml to exclude problematic migration file**
  ```yaml
  # sqlc.yaml
  sql:
    - schema: "sql/schema"
      queries: "sql/queries"
      engine: "postgresql"
      excludes:
        - "sql/schema/004_partition_crawl_log.sql"
      codegen:
        - plugin: py
          out: crawler/db/generated
          options:
            package: crawler.db.generated
            emit_sync_querier: false
            emit_async_querier: true
            emit_pydantic_models: true
            query_parameter_limit: 10
  ```

- [ ] **1.2: Regenerate sqlc code**
  ```bash
  make sqlc-generate
  # or
  sqlc generate
  ```

- [ ] **1.3: Verify `stream_logs_by_job()` method is generated**
  ```bash
  grep -n "def stream_logs_by_job" crawler/db/generated/crawl_log.py
  ```

- [ ] **1.4: Refactor `CrawlLogRepository.stream_logs_by_job()` to use generated method**
  - Remove manual SQL query and row construction
  - Replace with `self._querier.stream_logs_by_job()`
  - Add `# type: ignore[arg-type]` for optional log_level parameter
  - Pattern:
    ```python
    logs = [
        log async for log in self._querier.stream_logs_by_job(
            job_id=to_uuid(job_id),
            after_timestamp=after_timestamp,
            log_level=log_level,  # type: ignore[arg-type]
            limit_count=limit,
        )
    ]
    return logs
    ```

- [ ] **1.5: Run tests to verify functionality**
  ```bash
  uv run pytest tests/unit/repositories/test_crawl_log_repository.py -v
  uv run pytest tests/integration/test_websocket_logs.py -v
  uv run pytest tests/integration/test_nats_log_streaming.py -v
  ```

- [ ] **1.6: Commit changes**
  ```bash
  git add sqlc.yaml crawler/db/repositories/crawl_log.py
  git commit -m "fix: exclude migration file from sqlc, use generated stream_logs_by_job"
  ```

---

## Phase 2: Directory Restructure (Next Sprint - 2-3 hours)

### ✅ Objective
Separate schema definitions from migrations for long-term maintainability.

### Tasks

- [ ] **2.1: Create new directory structure**
  ```bash
  mkdir -p sql/migrations
  mkdir -p sql/schema_backup
  ```

- [ ] **2.2: Backup current schema files**
  ```bash
  cp -r sql/schema/* sql/schema_backup/
  ```

- [ ] **2.3: Move migration files to migrations directory**
  ```bash
  mv sql/schema/001_initial.sql sql/migrations/
  mv sql/schema/002_add_indexes.sql sql/migrations/
  mv sql/schema/003_add_retention.sql sql/migrations/
  mv sql/schema/004_partition_crawl_log.sql sql/migrations/
  # Keep any future 00*.sql files pattern
  ```

- [ ] **2.4: Generate current schema state from database**

  **Option A: From production/staging DB**
  ```bash
  # Connect to database and dump schema only
  pg_dump --schema-only \
          --no-owner \
          --no-privileges \
          --no-tablespaces \
          postgresql://user:pass@host:5432/dbname \
          > sql/schema/current_schema.sql
  ```

  **Option B: From local test DB**
  ```bash
  # Run all migrations first
  psql -f sql/migrations/001_initial.sql
  psql -f sql/migrations/002_add_indexes.sql
  psql -f sql/migrations/003_add_retention.sql
  psql -f sql/migrations/004_partition_crawl_log.sql

  # Then dump
  pg_dump --schema-only --no-owner --no-privileges \
          postgresql://localhost:5432/crawler_test \
          > sql/schema/current_schema.sql
  ```

- [ ] **2.5: Clean up generated schema file**
  - Remove `SET` commands and session variables
  - Remove comments about dump date/version
  - Keep only CREATE TABLE, CREATE TYPE, CREATE INDEX, ALTER TABLE
  - Organize in logical order: TYPES → TABLES → INDEXES → CONSTRAINTS

- [ ] **2.6: Update sqlc.yaml (remove excludes)**
  ```yaml
  sql:
    - schema: "sql/schema"  # Now contains only clean schema
      queries: "sql/queries"
      engine: "postgresql"
      # No excludes needed anymore!
      codegen:
        - plugin: py
          out: crawler/db/generated
          options:
            package: crawler.db.generated
            emit_sync_querier: false
            emit_async_querier: true
            emit_pydantic_models: true
            query_parameter_limit: 10
  ```

- [ ] **2.7: Regenerate all sqlc code**
  ```bash
  rm -rf crawler/db/generated/*
  make sqlc-generate
  ```

- [ ] **2.8: Update documentation**
  - [ ] Update README.md with new directory structure
  - [ ] Add `sql/migrations/README.md` explaining migration workflow
  - [ ] Add `sql/schema/README.md` explaining that it's auto-generated
  - [ ] Update CLAUDE.md with new patterns

- [ ] **2.9: Update Makefile targets**
  ```makefile
  # Add new target for schema regeneration
  .PHONY: regenerate-schema
  regenerate-schema:  ## Regenerate schema from database
  	@echo "⚙️  Regenerating schema from database..."
  	pg_dump --schema-only --no-owner --no-privileges \
  		$(DATABASE_URL) > sql/schema/current_schema.sql
  	@echo "✅ Schema regenerated"
  ```

- [ ] **2.10: Run full test suite**
  ```bash
  uv run pytest tests/ -v
  ```

- [ ] **2.11: Commit phase 2 changes**
  ```bash
  git add sql/ sqlc.yaml Makefile README.md docs/
  git commit -m "refactor: separate schema definitions from migrations"
  ```

---

## Phase 3: Adopt Migration Tool (Future - 1-2 hours)

### ✅ Objective
Replace manual SQL migrations with Alembic for version control, dependency tracking, and rollback capability.

### Tasks

- [ ] **3.1: Install Alembic**
  ```bash
  uv add alembic
  # or
  pip install alembic
  ```

- [ ] **3.2: Initialize Alembic**
  ```bash
  alembic init alembic
  ```

- [ ] **3.3: Configure Alembic for async SQLAlchemy**

  **Edit `alembic/env.py`:**
  ```python
  from crawler.db.session import async_engine
  from crawler.db.models import Base  # If using SQLAlchemy models

  # Update target_metadata
  target_metadata = Base.metadata

  # Configure for async
  def run_migrations_online():
      connectable = async_engine

      with connectable.connect() as connection:
          context.configure(
              connection=connection,
              target_metadata=target_metadata
          )

          with context.begin_transaction():
              context.run_migrations()
  ```

- [ ] **3.4: Mark current state as baseline**
  ```bash
  # Stamp current database with baseline revision
  alembic stamp head
  ```

- [ ] **3.5: Create migration tracking table**
  - Alembic creates `alembic_version` table automatically
  - Verify with: `psql -c "\dt alembic_version"`

- [ ] **3.6: Test auto-generation**
  ```bash
  # Make a schema change in SQLAlchemy models
  # Then auto-generate migration
  alembic revision --autogenerate -m "Test migration"

  # Review generated migration in alembic/versions/
  # Apply migration
  alembic upgrade head
  ```

- [ ] **3.7: Migrate existing migration files**
  - [ ] Convert `sql/migrations/001_initial.sql` to Alembic (already applied, mark as baseline)
  - [ ] Convert `sql/migrations/002_add_indexes.sql` to Alembic revision
  - [ ] Convert `sql/migrations/003_add_retention.sql` to Alembic revision
  - [ ] Convert `sql/migrations/004_partition_crawl_log.sql` to Alembic revision

- [ ] **3.8: Update deployment process**
  - [ ] Add `alembic upgrade head` to startup scripts
  - [ ] Add to Docker entrypoint
  - [ ] Add to CI/CD pipeline
  - [ ] Document rollback procedure: `alembic downgrade -1`

- [ ] **3.9: Document new migration workflow**
  ```markdown
  # Creating New Migrations

  1. Make schema changes in SQLAlchemy models (if using ORM)
  2. Generate migration: `alembic revision --autogenerate -m "description"`
  3. Review generated migration in `alembic/versions/`
  4. Test migration: `alembic upgrade head`
  5. Test rollback: `alembic downgrade -1`
  6. Commit migration file

  # Applying Migrations

  - Development: `alembic upgrade head`
  - Production: Run via deployment script
  - Rollback: `alembic downgrade -1` or `alembic downgrade <revision>`
  ```

- [ ] **3.10: Update CLAUDE.md with new patterns**
  ```markdown
  ## Database Migrations

  - Use Alembic for all schema changes
  - Never manually edit `sql/schema/current_schema.sql`
  - Auto-generate migrations: `alembic revision --autogenerate`
  - Always review auto-generated migrations before applying
  ```

- [ ] **3.11: Commit phase 3 changes**
  ```bash
  git add alembic/ pyproject.toml docs/
  git commit -m "feat: adopt Alembic for database migrations"
  ```

---

## Testing Strategy

### After Each Phase

**Phase 1 Tests:**
```bash
# Verify sqlc generation works
make sqlc-generate

# Verify generated method exists
grep "def stream_logs_by_job" crawler/db/generated/crawl_log.py

# Run repository tests
uv run pytest tests/unit/repositories/test_crawl_log_repository.py -v

# Run WebSocket tests (uses stream_logs_by_job)
uv run pytest tests/integration/test_websocket_logs.py -v
uv run pytest tests/integration/test_nats_log_streaming.py -v
```

**Phase 2 Tests:**
```bash
# Verify sqlc still works with new structure
make sqlc-generate

# Run all database tests
uv run pytest tests/unit/repositories/ -v
uv run pytest tests/integration/ -v

# Verify no regressions
uv run pytest tests/ --maxfail=3
```

**Phase 3 Tests:**
```bash
# Test Alembic migration
alembic upgrade head
alembic current
alembic downgrade -1
alembic upgrade head

# Test auto-generation (make small change first)
alembic revision --autogenerate -m "test"

# Run full test suite
uv run pytest tests/ -v
```

---

## Success Criteria

### Phase 1
- ✅ sqlc generates without errors
- ✅ `stream_logs_by_job()` method exists in generated code
- ✅ All tests pass
- ✅ No manual SQL in `CrawlLogRepository.stream_logs_by_job()`

### Phase 2
- ✅ Clear separation: `sql/schema/` (static) vs `sql/migrations/` (evolution)
- ✅ sqlc generates from clean schema without excludes
- ✅ All generated code matches previous output
- ✅ Documentation updated
- ✅ All tests pass

### Phase 3
- ✅ Alembic properly configured for async SQLAlchemy
- ✅ Can auto-generate migrations from model changes
- ✅ Can apply and rollback migrations
- ✅ Migration history tracked in database
- ✅ Deployment process updated
- ✅ All tests pass

---

## Rollback Plan

### Phase 1 Rollback
```bash
# Remove excludes from sqlc.yaml
git checkout HEAD -- sqlc.yaml

# Revert repository changes
git checkout HEAD -- crawler/db/repositories/crawl_log.py
```

### Phase 2 Rollback
```bash
# Restore original structure
mv sql/migrations/* sql/schema/
rmdir sql/migrations

# Restore original sqlc.yaml
git checkout HEAD -- sqlc.yaml

# Regenerate
make sqlc-generate
```

### Phase 3 Rollback
```bash
# Remove Alembic
uv remove alembic
rm -rf alembic/

# Keep manual migrations
# (sql/migrations/ still exists from Phase 2)
```

---

## References

- [sqlc Documentation](https://docs.sqlc.dev)
- [Alembic Documentation](https://alembic.sqlalchemy.org)
- [PostgreSQL Partitioning](https://www.postgresql.org/docs/current/ddl-partitioning.html)
- [Django Migrations](https://docs.djangoproject.com/en/stable/topics/migrations/)
- [Rails Migrations](https://guides.rubyonrails.org/active_record_migrations.html)

---

## Notes

- **Phase 1** is the quick fix to unblock development
- **Phase 2** is the structural improvement for long-term maintainability
- **Phase 3** is the professional-grade solution with proper tooling
- Each phase is independent and can be done separately
- Phases can be spread across multiple sprints
- All phases are backward compatible with existing functionality

---

## Updates

| Date | Phase | Status | Notes |
|------|-------|--------|-------|
| 2025-11-07 | Planning | Complete | TODO created |
| 2025-11-07 | Phase 1 | Complete | sqlc unblocked, stream_logs_by_job using generated code |
| 2025-11-07 | Phase 2 | Complete | Schema/migrations separated, regenerate-schema target added |
| 2025-11-07 | Phase 3 | Complete | Alembic configured for async SQLAlchemy, tested upgrade/downgrade |

---

**Last Updated**: 2025-11-07
**Created By**: Claude Code
**Completed By**: Claude Code
