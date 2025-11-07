#!/usr/bin/env python3
"""Run Alembic migrations before application startup.

This script should be executed before starting the FastAPI application to ensure
the database schema is up to date. It's designed to be used in:
- Docker entrypoints
- CI/CD pipelines
- Deployment scripts
- Local development startup

Usage:
    python scripts/run_migrations.py
    # or
    uv run python scripts/run_migrations.py
"""

import sys
from pathlib import Path

from alembic.config import Config

from alembic import command

# Add project root to path so we can import settings
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from crawler.core.logging import get_logger  # noqa: E402

logger = get_logger(__name__)


def run_migrations() -> None:
    """Run Alembic migrations to upgrade database to head.

    Raises:
        Exception: If migrations fail to apply.
    """
    try:
        logger.info("migration_check_start", message="Checking for pending migrations")

        # Create Alembic config
        alembic_ini = project_root / "alembic.ini"
        if not alembic_ini.exists():
            logger.error(
                "alembic_config_not_found",
                path=str(alembic_ini),
                message="alembic.ini not found",
            )
            sys.exit(1)

        alembic_cfg = Config(str(alembic_ini))

        # Run migrations to head
        logger.info("migration_upgrade_start", message="Applying migrations")
        command.upgrade(alembic_cfg, "head")

        logger.info("migration_upgrade_complete", message="All migrations applied successfully")

    except Exception as e:
        logger.error(
            "migration_failed",
            error=str(e),
            error_type=type(e).__name__,
            message="Failed to run migrations",
        )
        sys.exit(1)


if __name__ == "__main__":
    run_migrations()
