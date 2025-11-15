"""extend crawl_job for inline config support

Revision ID: 948eebe0b228
Revises: 356b49daa767
Create Date: 2025-11-07 22:46:31.511710


Changes:
- Make website_id nullable (support inline config without template)
- Rename embedded_config to inline_config
- Add constraint: exactly one of website_id or inline_config must be set
- Add GIN index on inline_config
- Add partial index for inline config jobs

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "948eebe0b228"
down_revision: str | Sequence[str] | None = "356b49daa767"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - split into individual statements for asyncpg compatibility."""
    # Make website_id nullable
    op.execute("ALTER TABLE crawl_job ALTER COLUMN website_id DROP NOT NULL")

    # Rename embedded_config to inline_config
    op.execute("ALTER TABLE crawl_job RENAME COLUMN embedded_config TO inline_config")

    # Add XOR constraint: exactly one of website_id or inline_config must be set
    op.execute("""
        ALTER TABLE crawl_job
        ADD CONSTRAINT ck_crawl_job_config_source CHECK (
            num_nonnulls(website_id, inline_config) = 1
        )
    """)

    # Create GIN index on inline_config for queries within configuration
    op.execute("""
        CREATE INDEX ix_crawl_job_inline_config ON crawl_job USING gin(inline_config)
        WHERE inline_config IS NOT NULL
    """)

    # Create partial index optimized for GetInlineConfigJobs query
    op.execute("""
        CREATE INDEX ix_crawl_job_inline_config_jobs ON crawl_job(created_at DESC)
        WHERE website_id IS NULL AND inline_config IS NOT NULL
    """)

    # Add comments
    op.execute(
        "COMMENT ON COLUMN crawl_job.website_id IS "
        "'Reference to website template (nullable for inline config jobs)'"
    )

    op.execute(
        "COMMENT ON COLUMN crawl_job.inline_config IS "
        "'Inline configuration for jobs without website template'"
    )

    op.execute(
        "COMMENT ON CONSTRAINT ck_crawl_job_config_source ON crawl_job IS "
        "'Ensures exactly one of website_id or inline_config is set (mutually exclusive)'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP INDEX IF EXISTS ix_crawl_job_inline_config_jobs")
    op.execute("DROP INDEX IF EXISTS ix_crawl_job_inline_config")
    op.execute("ALTER TABLE crawl_job DROP CONSTRAINT IF EXISTS ck_crawl_job_config_source")
    op.execute("ALTER TABLE crawl_job RENAME COLUMN inline_config TO embedded_config")
    op.execute("ALTER TABLE crawl_job ALTER COLUMN website_id SET NOT NULL")
