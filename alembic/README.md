# Alembic Database Migrations

This directory contains Alembic migration files for managing database schema changes.

## Configuration

- **`alembic.ini`** - Alembic configuration file
- **`env.py`** - Migration environment (configured for async SQLAlchemy)
- **`versions/`** - Migration version files

## Database URL

The database URL is loaded from your `.env` file via `config.settings.get_settings()`.

## Common Commands

### Check Current Revision

```bash
uv run alembic current
```

### Create a New Migration

```bash
# Manual migration (empty template)
uv run alembic revision -m "description of change"

# Auto-generate migration (requires SQLAlchemy models)
uv run alembic revision --autogenerate -m "description"
```

**Note**: Since we use sqlc (not SQLAlchemy ORM), autogenerate won't work. Create manual migrations.

### Apply Migrations

```bash
# Upgrade to latest (head)
uv run alembic upgrade head

# Upgrade by one version
uv run alembic upgrade +1

# Upgrade to specific revision
uv run alembic upgrade <revision_id>
```

### Rollback Migrations

```bash
# Downgrade by one version
uv run alembic downgrade -1

# Downgrade to specific revision
uv run alembic downgrade <revision_id>

# Downgrade all (back to base)
uv run alembic downgrade base
```

### View Migration History

```bash
# Show current revision
uv run alembic current

# Show migration history
uv run alembic history

# Show detailed history with range
uv run alembic history -r-3:
```

## Migration Workflow

1. **Create migration**:
   ```bash
   uv run alembic revision -m "add_user_profile_table"
   ```

2. **Edit the generated file** in `alembic/versions/`:
   ```python
   def upgrade() -> None:
       op.create_table(
           'user_profile',
           sa.Column('id', sa.UUID(), primary_key=True),
           sa.Column('user_id', sa.UUID(), nullable=False),
           # ... more columns
       )

   def downgrade() -> None:
       op.drop_table('user_profile')
   ```

3. **Test locally**:
   ```bash
   # Apply migration
   uv run alembic upgrade head

   # Test rollback
   uv run alembic downgrade -1

   # Re-apply
   uv run alembic upgrade head
   ```

4. **Update static schema** (after migration):
   ```bash
   make regenerate-schema
   make sqlc-generate
   ```

5. **Run tests**:
   ```bash
   uv run pytest
   ```

6. **Commit**:
   ```bash
   git add alembic/versions/ sql/schema/current_schema.sql
   git commit -m "feat: add user_profile table"
   ```

## Deployment

Migrations should be applied automatically during deployment:

```bash
uv run alembic upgrade head
```

Add this to your deployment script or Docker entrypoint.

## Best Practices

1. **Always test rollback** - Ensure `downgrade()` works
2. **Keep migrations small** - One logical change per migration
3. **Never modify existing migrations** - Create a new one instead
4. **Document breaking changes** - Add comments for complex migrations
5. **Update static schema** - Run `make regenerate-schema` after applying migrations
6. **Check production first** - Use `alembic current` to verify state

## Baseline Migration

The initial migrations represent the schema that was originally created with manual SQL files. All migrations are now managed exclusively through Alembic.

## Async SQLAlchemy

This Alembic setup is configured for async SQLAlchemy:

- Uses `async_engine_from_config`
- Runs migrations via `connection.run_sync()`
- Compatible with asyncpg driver

## Troubleshooting

### Migration fails to apply

Check that:
1. Database is running: `make db-up`
2. Connection string is correct in `.env`
3. You're on the correct revision: `uv run alembic current`

### Rollback fails

Some operations can't be rolled back automatically (e.g., dropping data). Implement custom rollback logic in `downgrade()`.

### "revision not found"

Reset to head:
```bash
uv run alembic stamp head
```

## See Also

- `sql/schema/README.md` - Static schema documentation
- [Alembic Documentation](https://alembic.sqlalchemy.org/)
