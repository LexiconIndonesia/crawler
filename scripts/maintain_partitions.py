#!/usr/bin/env python3
"""Partition maintenance script for crawl_log table.

This script manages monthly partitions for the crawl_log table:
- Creates future partitions based on configuration
- Drops old partitions based on retention policy
- Can be run manually or scheduled via cron

Usage:
    # Create future partitions (uses settings.log_partition_months_ahead)
    python scripts/maintain_partitions.py create-future

    # Drop old partitions (uses settings.log_retention_days)
    python scripts/maintain_partitions.py drop-old

    # Run both operations (create + drop)
    python scripts/maintain_partitions.py maintain

    # Show partition information
    python scripts/maintain_partitions.py list

Recommended cron schedule (run monthly):
    0 0 1 * * /path/to/python /path/to/scripts/maintain_partitions.py maintain
"""

import argparse
import asyncio
import sys
from pathlib import Path

import asyncpg

# Add parent directory to path to import from config
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import get_settings
from crawler.core.logging import get_logger

logger = get_logger(__name__)


async def get_connection() -> asyncpg.Connection:
    """Get database connection.

    Returns:
        Database connection.
    """
    settings = get_settings()
    # Convert SQLAlchemy URL to asyncpg connection string
    db_url = str(settings.database_url).replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(db_url)


async def create_future_partitions(conn: asyncpg.Connection, months_ahead: int) -> None:
    """Create future partitions for the specified number of months.

    Args:
        conn: Database connection.
        months_ahead: Number of months ahead to create partitions.
    """
    logger.info("create_future_partitions_start", months_ahead=months_ahead)

    try:
        # Call the PostgreSQL function to create future partitions
        results = await conn.fetch("SELECT create_future_crawl_log_partitions($1)", months_ahead)

        for row in results:
            result_msg = row["result"]
            logger.info("partition_created", message=result_msg)
            print(f"✓ {result_msg}")

        logger.info(
            "create_future_partitions_complete",
            months_ahead=months_ahead,
            partitions_processed=len(results),
        )

    except Exception as e:
        logger.error("create_future_partitions_failed", error=str(e))
        raise


async def drop_old_partitions(conn: asyncpg.Connection, retention_days: int) -> None:
    """Drop old partitions based on retention policy.

    Args:
        conn: Database connection.
        retention_days: Number of days to retain data.
    """
    logger.info("drop_old_partitions_start", retention_days=retention_days)

    try:
        # Call the PostgreSQL function to drop old partitions
        # Returns structured data: (status, partition_name, message)
        results = await conn.fetch(
            "SELECT * FROM drop_old_crawl_log_partitions($1)", retention_days
        )

        dropped_count = 0
        error_count = 0

        for row in results:
            status = row["status"]
            partition_name = row["partition_name"]
            message = row["message"]

            if status == "dropped":
                dropped_count += 1
                logger.info(
                    "partition_dropped",
                    partition=partition_name,
                    message=message,
                )
                print(f"✓ {partition_name}: {message}")

            elif status == "error":
                error_count += 1
                logger.error(
                    "partition_drop_error",
                    partition=partition_name,
                    message=message,
                )
                print(f"⚠ {partition_name}: {message}")

            # status == "skipped" is silently ignored (within retention)

        if dropped_count == 0 and error_count == 0:
            logger.info("no_partitions_to_drop", retention_days=retention_days)
            print(f"✓ No partitions older than {retention_days} days to drop")

        logger.info(
            "drop_old_partitions_complete",
            retention_days=retention_days,
            partitions_dropped=dropped_count,
            errors=error_count,
        )

    except Exception as e:
        logger.error("drop_old_partitions_failed", error=str(e))
        raise


async def list_partitions(conn: asyncpg.Connection) -> None:
    """List all existing partitions with metadata.

    Args:
        conn: Database connection.
    """
    logger.info("list_partitions_start")

    try:
        # Query the partition view
        results = await conn.fetch(
            """
            SELECT
                partition_name,
                partition_month,
                size,
                index_count
            FROM crawl_log_partitions
            ORDER BY partition_month DESC
            """
        )

        if not results:
            print("No partitions found")
            return

        # Print header
        print("\n{:<30} {:<15} {:<12} {:<10}".format("Partition Name", "Month", "Size", "Indexes"))
        print("-" * 70)

        # Print rows
        for row in results:
            print(
                "{:<30} {:<15} {:<12} {:<10}".format(
                    row["partition_name"],
                    row["partition_month"].strftime("%Y-%m") if row["partition_month"] else "N/A",
                    row["size"] or "N/A",
                    row["index_count"] or 0,
                )
            )

        print(f"\nTotal partitions: {len(results)}\n")
        logger.info("list_partitions_complete", partition_count=len(results))

    except Exception as e:
        logger.error("list_partitions_failed", error=str(e))
        raise


async def maintain_partitions(
    conn: asyncpg.Connection,
    months_ahead: int,
    retention_days: int,
) -> None:
    """Run full maintenance: create future partitions and drop old ones.

    Args:
        conn: Database connection.
        months_ahead: Number of months ahead to create partitions.
        retention_days: Number of days to retain data.
    """
    logger.info(
        "partition_maintenance_start",
        months_ahead=months_ahead,
        retention_days=retention_days,
    )

    print("=" * 70)
    print("Partition Maintenance")
    print("=" * 70)

    print("\n1. Creating future partitions...")
    await create_future_partitions(conn, months_ahead)

    print("\n2. Dropping old partitions...")
    await drop_old_partitions(conn, retention_days)

    print("\n3. Current partition status:")
    await list_partitions(conn)

    logger.info("partition_maintenance_complete")
    print("=" * 70)
    print("✓ Partition maintenance completed successfully")
    print("=" * 70)


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage crawl_log table partitions",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "command",
        choices=["create-future", "drop-old", "maintain", "list"],
        help="Command to execute",
    )

    parser.add_argument(
        "--months-ahead",
        type=int,
        help="Override log_partition_months_ahead setting",
    )

    parser.add_argument(
        "--retention-days",
        type=int,
        help="Override log_retention_days setting",
    )

    args = parser.parse_args()

    # Load settings
    settings = get_settings()

    # Use CLI args or fall back to settings
    months_ahead = args.months_ahead or settings.log_partition_months_ahead
    retention_days = args.retention_days or settings.log_retention_days

    # Connect to database
    conn = await get_connection()

    try:
        if args.command == "create-future":
            await create_future_partitions(conn, months_ahead)

        elif args.command == "drop-old":
            await drop_old_partitions(conn, retention_days)

        elif args.command == "maintain":
            await maintain_partitions(conn, months_ahead, retention_days)

        elif args.command == "list":
            await list_partitions(conn)

    except Exception as e:
        logger.error("partition_maintenance_error", error=str(e))
        print(f"\n❌ Error: {e}", file=sys.stderr)
        sys.exit(1)

    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
