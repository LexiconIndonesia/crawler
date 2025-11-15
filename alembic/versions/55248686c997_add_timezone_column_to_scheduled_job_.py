"""add timezone column to scheduled_job table

Revision ID: 55248686c997
Revises: 8ceb0f6003cf
Create Date: 2025-11-15 19:37:52.655601

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "55248686c997"
down_revision: str | Sequence[str] | None = "8ceb0f6003cf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add timezone column with UTC as default for existing rows
    op.execute("""
        ALTER TABLE scheduled_job
        ADD COLUMN timezone VARCHAR(64) NOT NULL DEFAULT 'UTC'
    """)

    # Add check constraint to validate IANA timezone format
    op.execute("""
        ALTER TABLE scheduled_job
        ADD CONSTRAINT ck_scheduled_job_valid_timezone
        CHECK (timezone ~ '^[A-Za-z]+(/[A-Za-z_]+)?$')
    """)

    # Add column comment for documentation
    op.execute("""
        COMMENT ON COLUMN scheduled_job.timezone IS
        'IANA timezone name (e.g., UTC, America/New_York, Asia/Jakarta) for schedule calculations'
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop check constraint first
    op.execute("""
        ALTER TABLE scheduled_job
        DROP CONSTRAINT IF EXISTS ck_scheduled_job_valid_timezone
    """)

    # Drop timezone column
    op.execute("""
        ALTER TABLE scheduled_job
        DROP COLUMN IF EXISTS timezone
    """)
