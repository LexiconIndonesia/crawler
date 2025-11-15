"""add dead letter queue table

Revision ID: 8ceb0f6003cf
Revises: 7992dcb6a14b
Create Date: 2025-11-14 22:35:39.297905

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "8ceb0f6003cf"
down_revision: str | Sequence[str] | None = "7992dcb6a14b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create dead_letter_queue table for permanently failed jobs
    op.execute("""
        CREATE TABLE dead_letter_queue (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES crawl_job(id) ON DELETE CASCADE,

            -- Job metadata at time of failure
            seed_url TEXT NOT NULL,
            website_id UUID REFERENCES website(id) ON DELETE SET NULL,
            job_type job_type_enum NOT NULL,
            priority INTEGER NOT NULL,

            -- Failure information
            error_category error_category_enum NOT NULL,
            error_message TEXT NOT NULL,
            stack_trace TEXT,
            http_status INTEGER,

            -- Retry history summary
            total_attempts INTEGER NOT NULL,
            first_attempt_at TIMESTAMPTZ NOT NULL,
            last_attempt_at TIMESTAMPTZ NOT NULL,

            -- DLQ management
            added_to_dlq_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            retry_attempted BOOLEAN NOT NULL DEFAULT FALSE,
            retry_attempted_at TIMESTAMPTZ,
            retry_success BOOLEAN,
            resolved_at TIMESTAMPTZ,
            resolution_notes TEXT,

            -- Constraints
            CONSTRAINT ck_dlq_total_attempts CHECK (total_attempts > 0),
            CONSTRAINT ck_dlq_retry_logic
                CHECK (
                    (retry_attempted = FALSE AND retry_attempted_at IS NULL) OR
                    (retry_attempted = TRUE AND retry_attempted_at IS NOT NULL)
                )
        )
    """)

    # Create indexes for DLQ queries
    op.execute("CREATE INDEX idx_dlq_job_id ON dead_letter_queue(job_id)")
    op.execute("CREATE INDEX idx_dlq_added_at ON dead_letter_queue(added_to_dlq_at DESC)")
    op.execute("CREATE INDEX idx_dlq_error_category ON dead_letter_queue(error_category)")
    op.execute("CREATE INDEX idx_dlq_website_id ON dead_letter_queue(website_id)")
    op.execute(
        "CREATE INDEX idx_dlq_unresolved ON dead_letter_queue(added_to_dlq_at DESC) "
        "WHERE resolved_at IS NULL"
    )
    op.execute(
        "CREATE INDEX idx_dlq_retry_pending ON dead_letter_queue(added_to_dlq_at) "
        "WHERE retry_attempted = FALSE"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("DROP TABLE IF EXISTS dead_letter_queue CASCADE")
