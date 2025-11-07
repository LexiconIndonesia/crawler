"""add scheduled jobs support

Revision ID: 356b49daa767
Revises: 7ae2337d8974
Create Date: 2025-11-07 22:45:41.158952

Corresponds to sql/migrations/002_scheduled_jobs.sql

Adds:
- cron_schedule column to website table
- scheduled_job table with cron scheduling
- Indexes for efficient scheduling queries

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "356b49daa767"
down_revision: str | Sequence[str] | None = "7ae2337d8974"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - split into individual statements for asyncpg compatibility."""
    # Add cron_schedule column to website table
    op.execute(
        "ALTER TABLE website ADD COLUMN cron_schedule VARCHAR(255) DEFAULT '0 0 1,15 * *'"
    )

    op.execute("""
        COMMENT ON COLUMN website.cron_schedule IS
            'Default cron schedule expression for this website '
            '(default: "0 0 1,15 * *" runs on 1st and 15th at midnight, '
            'approximately every 2 weeks)'
    """)

    # Create scheduled_job table
    op.execute("""
        CREATE TABLE scheduled_job (
            id UUID PRIMARY KEY DEFAULT uuidv7(),
            website_id UUID NOT NULL REFERENCES website(id) ON DELETE CASCADE,
            cron_schedule VARCHAR(255) NOT NULL,
            next_run_time TIMESTAMPTZ NOT NULL,
            last_run_time TIMESTAMPTZ,
            is_active BOOLEAN NOT NULL DEFAULT true,
            job_config JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_scheduled_job_valid_cron CHECK (
                cron_schedule ~
                '^(\\*|[0-9,\\-/]+)\\s+(\\*|[0-9,\\-/]+)\\s+(\\*|[0-9,\\-/]+)\\s+'
                '(\\*|[0-9,\\-/]+|[A-Z]{3})\\s+(\\*|[0-9,\\-/]+|[A-Z]{3})'
                '(\\s+(\\*|[0-9,\\-/]+))?$'
            )
        )
    """)

    # Add comments to table and columns
    op.execute(
        "COMMENT ON TABLE scheduled_job IS "
        "'Stores scheduled crawl job configurations with cron schedules'"
    )

    op.execute(
        "COMMENT ON COLUMN scheduled_job.cron_schedule IS "
        "'Cron expression defining when the job should run'"
    )

    op.execute(
        "COMMENT ON COLUMN scheduled_job.next_run_time IS 'Next scheduled execution time'"
    )

    op.execute(
        "COMMENT ON COLUMN scheduled_job.last_run_time IS 'Most recent execution time'"
    )

    op.execute(
        "COMMENT ON COLUMN scheduled_job.is_active IS "
        "'Flag to pause/resume schedule without deleting'"
    )

    op.execute(
        "COMMENT ON COLUMN scheduled_job.job_config IS 'Job-specific configuration overrides'"
    )

    # Create indexes
    op.execute("CREATE INDEX ix_scheduled_job_website_id ON scheduled_job(website_id)")
    op.execute(
        "CREATE INDEX ix_scheduled_job_next_run_time ON scheduled_job(next_run_time)"
    )
    op.execute("CREATE INDEX ix_scheduled_job_is_active ON scheduled_job(is_active)")

    op.execute("""
        CREATE INDEX ix_scheduled_job_active_next_run
        ON scheduled_job(is_active, next_run_time)
        WHERE is_active = true
    """)

    op.execute(
        "COMMENT ON INDEX ix_scheduled_job_active_next_run IS "
        "'Optimized index for finding next jobs to execute'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS scheduled_job CASCADE")
    op.execute("ALTER TABLE website DROP COLUMN IF EXISTS cron_schedule")
