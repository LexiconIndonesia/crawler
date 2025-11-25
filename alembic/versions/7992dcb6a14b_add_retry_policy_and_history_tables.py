"""add retry policy and history tables

Revision ID: 7992dcb6a14b
Revises: c7f64249dfa2
Create Date: 2025-11-14 17:34:14.924232

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7992dcb6a14b"
down_revision: str | Sequence[str] | None = "c7f64249dfa2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create error_category_enum (if doesn't exist)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'error_category_enum') THEN
                CREATE TYPE error_category_enum AS ENUM (
                    'network',
                    'rate_limit',
                    'server_error',
                    'browser_crash',
                    'resource_unavailable',
                    'timeout',
                    'client_error',
                    'auth_error',
                    'not_found',
                    'validation_error',
                    'business_logic_error',
                    'unknown'
                );
            END IF;
        END $$
    """)

    # Create backoff_strategy_enum (if doesn't exist)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'backoff_strategy_enum') THEN
                CREATE TYPE backoff_strategy_enum AS ENUM (
                    'exponential',
                    'linear',
                    'fixed'
                );
            END IF;
        END $$
    """)

    # Create retry_policy table
    op.execute("""
        CREATE TABLE retry_policy (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            error_category error_category_enum NOT NULL UNIQUE,
            is_retryable BOOLEAN NOT NULL DEFAULT true,
            max_attempts INTEGER NOT NULL DEFAULT 3,
            backoff_strategy backoff_strategy_enum NOT NULL DEFAULT 'exponential',
            initial_delay_seconds INTEGER NOT NULL DEFAULT 1,
            max_delay_seconds INTEGER NOT NULL DEFAULT 300,
            backoff_multiplier FLOAT NOT NULL DEFAULT 2.0,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_retry_policy_max_attempts
                CHECK (max_attempts >= 0 AND max_attempts <= 10),
            CONSTRAINT ck_retry_policy_initial_delay
                CHECK (initial_delay_seconds >= 0 AND initial_delay_seconds <= 60),
            CONSTRAINT ck_retry_policy_max_delay
                CHECK (max_delay_seconds >= 0 AND max_delay_seconds <= 3600),
            CONSTRAINT ck_retry_policy_backoff_multiplier
                CHECK (backoff_multiplier >= 1.0 AND backoff_multiplier <= 10.0)
        )
    """)

    # Create index on retry_policy
    op.execute("CREATE INDEX idx_retry_policy_category ON retry_policy(error_category)")

    # Create retry_history table
    op.execute("""
        CREATE TABLE retry_history (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES crawl_job(id) ON DELETE CASCADE,
            attempt_number INTEGER NOT NULL,
            error_category error_category_enum NOT NULL,
            error_message TEXT NOT NULL,
            stack_trace TEXT,
            retry_delay_seconds INTEGER NOT NULL,
            attempted_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

            CONSTRAINT ck_retry_history_attempt_number CHECK (attempt_number > 0),
            CONSTRAINT ck_retry_history_retry_delay CHECK (retry_delay_seconds >= 0)
        )
    """)

    # Create indexes on retry_history
    op.execute("CREATE INDEX idx_retry_history_job_id ON retry_history(job_id)")
    op.execute("CREATE INDEX idx_retry_history_category ON retry_history(error_category)")
    op.execute("CREATE INDEX idx_retry_history_attempted_at ON retry_history(attempted_at)")
    op.execute(
        "CREATE INDEX idx_retry_history_job_attempt ON retry_history(job_id, attempt_number)"
    )

    # Seed default retry policies
    op.execute("""
        INSERT INTO retry_policy (
            error_category, is_retryable, max_attempts, backoff_strategy,
            initial_delay_seconds, max_delay_seconds, backoff_multiplier, description
        ) VALUES
            ('network', true, 3, 'exponential', 1, 300, 2.0,
             'Network connectivity issues, DNS failures'),
            ('rate_limit', true, 5, 'exponential', 2, 600, 2.0,
             'HTTP 429 rate limiting - longer backoff'),
            ('server_error', true, 3, 'exponential', 1, 300, 2.0,
             'HTTP 5xx server errors'),
            ('browser_crash', true, 3, 'exponential', 2, 300, 2.0,
             'Browser crashes, context lost'),
            ('resource_unavailable', true, 3, 'linear', 5, 60, 1.5,
             'Temporary resource exhaustion'),
            ('timeout', true, 2, 'linear', 5, 60, 1.5,
             'Page load or selector timeouts'),
            ('client_error', false, 0, 'fixed', 0, 0, 1.0,
             'HTTP 4xx errors (except 429)'),
            ('auth_error', false, 0, 'fixed', 0, 0, 1.0,
             'Authentication or authorization failures'),
            ('not_found', false, 0, 'fixed', 0, 0, 1.0,
             'HTTP 404 resource not found'),
            ('validation_error', false, 0, 'fixed', 0, 0, 1.0,
             'Configuration validation failures'),
            ('business_logic_error', false, 0, 'fixed', 0, 0, 1.0,
             'Business rule violations'),
            ('unknown', true, 1, 'fixed', 10, 10, 1.0,
             'Unclassified errors - single retry')
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
    -- Drop tables
    DROP TABLE IF EXISTS retry_history CASCADE;
    DROP TABLE IF EXISTS retry_policy CASCADE;

    -- Drop enums
    DROP TYPE IF EXISTS error_category_enum CASCADE;
    DROP TYPE IF EXISTS backoff_strategy_enum CASCADE;
    """)
