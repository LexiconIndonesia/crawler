#!/usr/bin/env python3
"""Database migration runner for SQL-based migrations.

⚠️ DEPRECATED: This script is deprecated in favor of Alembic migrations.
Use `alembic upgrade head` or `make db-migrate` instead.

This script is kept for reference only and should not be used for new migrations.
All new migrations should be created with: `alembic revision -m "description"`

Reads schema files directly from sql/schema/ as migrations.
Each .sql file in sql/schema/ is treated as a migration.
"""

import argparse
import asyncio
import hashlib
import re
import sys
from pathlib import Path

import asyncpg

from config import get_settings
from crawler.core.logging import get_logger

logger = get_logger(__name__)

SCHEMA_DIR = Path(__file__).parent.parent / "sql" / "schema"


async def get_connection() -> asyncpg.Connection:
    """Get database connection.

    Returns:
        Database connection.
    """
    settings = get_settings()
    # Convert SQLAlchemy URL to asyncpg connection string
    db_url = str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(db_url)


def extract_metadata(sql_content: str) -> dict[str, str]:
    """Extract metadata from SQL file comments.

    Looks for comments like:
    -- version: 001
    -- description: Initial schema
    -- requires: PostgreSQL 18+

    Args:
        sql_content: Content of SQL file.

    Returns:
        Dictionary with metadata.
    """
    metadata = {}
    for line in sql_content.split("\n"):
        if line.startswith("--"):
            match = re.match(r"--\s*(\w+):\s*(.+)", line)
            if match:
                metadata[match.group(1)] = match.group(2).strip()
    return metadata


def calculate_checksum(sql_content: str) -> str:
    """Calculate SHA256 checksum of SQL content.

    Args:
        sql_content: SQL file content.

    Returns:
        SHA256 hex digest.
    """
    return hashlib.sha256(sql_content.encode()).hexdigest()


async def ensure_migrations_table(conn: asyncpg.Connection) -> None:
    """Ensure schema_migrations table exists by executing 000_migration_tracking.sql.

    Args:
        conn: Database connection.
    """
    tracking_file = SCHEMA_DIR / "000_migration_tracking.sql"
    if tracking_file.exists():
        sql = tracking_file.read_text()
        await conn.execute(sql)
        logger.info("migrations_table_ensured")
    else:
        # Fallback if file doesn't exist
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                checksum VARCHAR(64)
            );
            """
        )
        logger.info("migrations_table_ensured_fallback")


async def get_applied_migrations(conn: asyncpg.Connection) -> dict[str, str]:
    """Get list of applied migrations with checksums.

    Args:
        conn: Database connection.

    Returns:
        Dict mapping version to checksum.
    """
    rows = await conn.fetch("SELECT version, checksum FROM schema_migrations ORDER BY version")
    return {row["version"]: row["checksum"] for row in rows}


def get_available_migrations() -> list[tuple[str, str, str, str]]:
    """Get list of available schema files as migrations.

    Returns:
        List of tuples: (version, description, filepath, checksum).
    """
    migrations = []
    for file_path in sorted(SCHEMA_DIR.glob("*.sql")):
        # Skip migration tracking file
        if file_path.name.startswith("000_"):
            continue

        # Read file and extract metadata
        sql_content = file_path.read_text()
        metadata = extract_metadata(sql_content)
        checksum = calculate_checksum(sql_content)

        version = metadata.get("version", file_path.stem.split("_")[0])
        description = metadata.get("description", file_path.stem)

        migrations.append((version, description, str(file_path), checksum))

    return migrations


async def apply_migration(
    conn: asyncpg.Connection, version: str, description: str, filepath: str, checksum: str
) -> None:
    """Apply a single migration from schema file.

    Args:
        conn: Database connection.
        version: Migration version.
        description: Migration description.
        filepath: Path to SQL schema file.
        checksum: SHA256 checksum of file content.
    """
    logger.info(
        "applying_migration",
        version=version,
        description=description,
        file=filepath,
        checksum=checksum,
    )

    # Read SQL file
    sql = Path(filepath).read_text()

    # Execute in transaction
    async with conn.transaction():
        await conn.execute(sql)

        # Record migration
        await conn.execute(
            """
            INSERT INTO schema_migrations (version, description, checksum)
            VALUES ($1, $2, $3)
            ON CONFLICT (version) DO UPDATE
            SET applied_at = CURRENT_TIMESTAMP,
                description = EXCLUDED.description,
                checksum = EXCLUDED.checksum
            """,
            version,
            description,
            checksum,
        )

    logger.info("migration_applied", version=version)


async def migrate_up(conn: asyncpg.Connection, target_version: str | None = None) -> None:
    """Apply pending migrations.

    Args:
        conn: Database connection.
        target_version: Optional target version to migrate to.
    """
    await ensure_migrations_table(conn)
    applied = await get_applied_migrations(conn)
    available = get_available_migrations()

    # Find pending migrations (not applied or checksum changed)
    pending = []
    for version, description, filepath, checksum in available:
        if version not in applied:
            # New migration
            pending.append((version, description, filepath, checksum))
        elif applied[version] != checksum:
            # Checksum changed - warn but allow (for development)
            logger.warning(
                "migration_checksum_changed",
                version=version,
                old_checksum=applied[version],
                new_checksum=checksum,
            )
            print(f"  ⚠️  Warning: Checksum changed for {version}")
            pending.append((version, description, filepath, checksum))

        # Stop at target version if specified
        if target_version and version > target_version:
            break

    if not pending:
        logger.info("no_pending_migrations")
        print("✓ No pending migrations")
        return

    print(f"Found {len(pending)} pending migration(s)")

    for version, description, filepath, checksum in pending:
        print(f"  → Applying {version}: {description}")
        await apply_migration(conn, version, description, filepath, checksum)
        print(f"  ✓ Applied {version}")

    print(f"\n✓ Successfully applied {len(pending)} migration(s)")


async def migrate_down(conn: asyncpg.Connection, steps: int = 1) -> None:
    """Rollback migrations.

    Note: This drops all tables and re-applies migrations up to target.

    Args:
        conn: Database connection.
        steps: Number of migrations to rollback.
    """
    await ensure_migrations_table(conn)
    applied = await get_applied_migrations(conn)

    if not applied:
        logger.info("no_migrations_to_rollback")
        print("✓ No migrations to rollback")
        return

    # Get migrations to keep
    versions_sorted = sorted(applied.keys())
    target_version = versions_sorted[-(steps + 1)] if steps < len(versions_sorted) else None

    print(f"⚠️  Warning: This will drop all tables and re-apply up to version {target_version}")
    print("Press Ctrl+C to cancel, or Enter to continue...")
    input()

    # Drop all tables
    async with conn.transaction():
        # Get all tables
        tables = await conn.fetch(
            """
            SELECT tablename FROM pg_tables
            WHERE schemaname = 'public'
            AND tablename != 'schema_migrations'
            """
        )

        for table in tables:
            await conn.execute(f"DROP TABLE IF EXISTS {table['tablename']} CASCADE")

        # Clear migrations except the ones we're keeping
        if target_version:
            await conn.execute("DELETE FROM schema_migrations WHERE version > $1", target_version)
        else:
            await conn.execute("TRUNCATE schema_migrations")

    print(f"✓ Rolled back {steps} migration(s)")


async def show_status(conn: asyncpg.Connection) -> None:
    """Show migration status.

    Args:
        conn: Database connection.
    """
    await ensure_migrations_table(conn)
    applied = await get_applied_migrations(conn)
    available = get_available_migrations()

    print("\nMigration Status")
    print("=" * 100)
    print(f"{'Status':<12} | {'Version':<8} | {'Checksum':<16} | {'Description'}")
    print("=" * 100)

    if not available:
        print("No schema files found in sql/schema/")
        return

    for version, description, filepath, checksum in available:
        if version in applied:
            if applied[version] == checksum:
                status = "✓ Applied"
            else:
                status = "⚠ Modified"
        else:
            status = "○ Pending"

        checksum_short = checksum[:14] + ".."
        print(f"{status:<12} | {version:<8} | {checksum_short:<16} | {description}")

    print("=" * 100)
    pending_count = sum(1 for v, _, _, _ in available if v not in applied)
    print(f"Applied: {len(applied)} | Pending: {pending_count} | Total: {len(available)}")


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Database migration runner")
    parser.add_argument(
        "command",
        choices=["up", "down", "status"],
        help="Migration command",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=1,
        help="Number of migrations to rollback (for 'down' command)",
    )
    parser.add_argument(
        "--version",
        type=str,
        help="Target version to migrate to (for 'up' command)",
    )

    args = parser.parse_args()

    try:
        conn = await get_connection()
        logger.info("database_connected")

        if args.command == "up":
            await migrate_up(conn, args.version)
        elif args.command == "down":
            await migrate_down(conn, args.steps)
        elif args.command == "status":
            await show_status(conn)

        await conn.close()
        logger.info("migration_complete", command=args.command)

    except Exception as e:
        logger.error("migration_failed", error=str(e), exc_info=True)
        print(f"\n✗ Migration failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
