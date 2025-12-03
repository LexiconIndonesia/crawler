"""convert crawl_log to partitioned table

Revision ID: 1d3ac885f5c4
Revises: 948eebe0b228
Create Date: 2025-11-07 22:48:27.115921


Converts crawl_log to use native PostgreSQL partitioning with:
- Monthly partitions for better query performance
- Partition management functions
- Automated partition creation for past, current, and future months
- Retention policy support (drop old partitions)
- Monitoring view for partition metadata

Benefits:
- Faster queries on recent data (partition pruning)
- Easier data retention (drop old partitions instead of DELETE)
- Better index maintenance (smaller partition-level indexes)
- Improved vacuum performance

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1d3ac885f5c4"
down_revision: str | Sequence[str] | None = "948eebe0b228"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - split into individual statements for asyncpg compatibility."""
    # STEP 1: Create partitioned table
    op.execute("ALTER TABLE crawl_log RENAME TO crawl_log_old")

    op.execute("""
        CREATE TABLE crawl_log (
            id BIGSERIAL,
            job_id UUID NOT NULL,
            website_id UUID NOT NULL,
            step_name VARCHAR(255),
            log_level log_level_enum NOT NULL DEFAULT 'INFO'::log_level_enum,
            message TEXT NOT NULL,
            context JSONB,
            trace_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (id, created_at)
        ) PARTITION BY RANGE (created_at)
    """)

    op.execute(
        "COMMENT ON TABLE crawl_log IS "
        "'Stores detailed crawl execution logs (partitioned by month)'"
    )

    # NOTE: Foreign keys cannot be added to partitioned tables in PostgreSQL.
    # They are added to each partition in create_crawl_log_partition function.

    # STEP 2: Create partition management functions
    op.execute("""
        CREATE OR REPLACE FUNCTION create_crawl_log_partition(partition_date DATE)
        RETURNS TEXT AS $$
        DECLARE
            partition_name TEXT;
            start_date DATE;
            end_date DATE;
        BEGIN
            start_date := DATE_TRUNC('month', partition_date);
            end_date := start_date + INTERVAL '1 month';
            partition_name := 'crawl_log_' || TO_CHAR(start_date, 'YYYY_MM');

            IF EXISTS (
                SELECT 1 FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE c.relname = partition_name
                AND n.nspname = 'public'
            ) THEN
                RETURN 'Partition ' || partition_name || ' already exists';
            END IF;

            EXECUTE format(
                'CREATE TABLE %I PARTITION OF crawl_log FOR VALUES FROM (%L) TO (%L)',
                partition_name,
                start_date,
                end_date
            );

            EXECUTE format('CREATE INDEX %I ON %I(job_id)',
                partition_name || '_job_id_idx', partition_name);
            EXECUTE format('CREATE INDEX %I ON %I(website_id)',
                partition_name || '_website_id_idx', partition_name);
            EXECUTE format('CREATE INDEX %I ON %I(log_level)',
                partition_name || '_log_level_idx', partition_name);
            EXECUTE format('CREATE INDEX %I ON %I(trace_id)',
                partition_name || '_trace_id_idx', partition_name);
            EXECUTE format('CREATE INDEX %I ON %I(job_id, created_at)',
                partition_name || '_job_created_idx', partition_name);

            -- Add foreign key constraints to the partition
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (job_id) REFERENCES crawl_job(id) ON DELETE CASCADE',
                partition_name, partition_name || '_job_id_fkey'
            );
            EXECUTE format(
                'ALTER TABLE %I ADD CONSTRAINT %I FOREIGN KEY (website_id) REFERENCES website(id) ON DELETE CASCADE',
                partition_name, partition_name || '_website_id_fkey'
            );

            RETURN 'Created partition ' || partition_name || ' for range [' ||
                   start_date || ', ' || end_date || ')';
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute(
        "COMMENT ON FUNCTION create_crawl_log_partition IS "
        "'Creates a monthly partition for crawl_log table with indexes'"
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION create_future_crawl_log_partitions(
            months_ahead INTEGER DEFAULT 3
        )
        RETURNS TABLE(result TEXT) AS $$
        DECLARE
            i INTEGER;
            partition_date DATE;
        BEGIN
            FOR i IN 0..months_ahead LOOP
                partition_date := CURRENT_DATE + (i || ' months')::INTERVAL;
                RETURN QUERY SELECT create_crawl_log_partition(partition_date);
            END LOOP;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute(
        "COMMENT ON FUNCTION create_future_crawl_log_partitions IS "
        "'Creates partitions for the next N months (default: 3)'"
    )

    op.execute("""
        CREATE OR REPLACE FUNCTION drop_old_crawl_log_partitions(
            retention_days INTEGER DEFAULT 90
        )
        RETURNS TABLE(
            status TEXT,
            partition_name TEXT,
            message TEXT
        ) AS $$
        DECLARE
            partition_record RECORD;
            cutoff_date DATE;
            partition_month DATE;
        BEGIN
            cutoff_date := CURRENT_DATE - retention_days;

            FOR partition_record IN
                SELECT tablename
                FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename LIKE 'crawl_log_%'
                AND tablename ~ '^crawl_log_[0-9]{4}_[0-9]{2}$'
            LOOP
                BEGIN
                    partition_month := TO_DATE(
                        SUBSTRING(
                            partition_record.tablename FROM 'crawl_log_([0-9]{4}_[0-9]{2})'
                        ),
                        'YYYY_MM'
                    );

                    IF partition_month < DATE_TRUNC('month', cutoff_date) THEN
                        EXECUTE format(
                            'DROP TABLE IF EXISTS %I CASCADE',
                            partition_record.tablename
                        );
                        RETURN QUERY SELECT
                            'dropped'::TEXT,
                            partition_record.tablename,
                            format('Dropped partition (older than %s days)', retention_days);
                    ELSE
                        RETURN QUERY SELECT
                            'skipped'::TEXT,
                            partition_record.tablename,
                            format('Partition kept (within retention period)');
                    END IF;
                EXCEPTION
                    WHEN OTHERS THEN
                        RETURN QUERY SELECT
                            'error'::TEXT,
                            partition_record.tablename,
                            'Error: ' || SQLERRM;
                END;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql
    """)

    op.execute(
        "COMMENT ON FUNCTION drop_old_crawl_log_partitions IS "
        "'Drops log partitions older than retention period (default: 90 days)'"
    )

    # STEP 3: Create initial partitions (past 3 months, current, next 3 months)
    op.execute("""
        DO $$
        DECLARE
            i INTEGER;
            partition_date DATE;
        BEGIN
            FOR i IN -3..3 LOOP
                partition_date := CURRENT_DATE + (i || ' months')::INTERVAL;
                PERFORM create_crawl_log_partition(partition_date);
            END LOOP;
        END;
        $$
    """)

    # STEP 4: Migrate data from old table
    op.execute("""
        INSERT INTO crawl_log (
            id, job_id, website_id, step_name, log_level,
            message, context, trace_id, created_at
        )
        SELECT
            id, job_id, website_id, step_name, log_level,
            message, context, trace_id, created_at
        FROM crawl_log_old
        ORDER BY created_at
    """)

    op.execute("SELECT setval('crawl_log_id_seq', (SELECT MAX(id) FROM crawl_log))")

    # STEP 5: Drop old table
    op.execute("DROP TABLE crawl_log_old CASCADE")

    # STEP 6: Create maintenance view
    op.execute("""
        CREATE OR REPLACE VIEW crawl_log_partitions AS
        SELECT
            schemaname,
            tablename as partition_name,
            TO_DATE(
                SUBSTRING(tablename FROM 'crawl_log_([0-9]{4}_[0-9]{2})'), 'YYYY_MM'
            ) as partition_month,
            pg_size_pretty(
                pg_total_relation_size(schemaname||'.'||tablename)
            ) as size,
            (SELECT COUNT(*) FROM pg_class c
             JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE c.relname = tablename AND n.nspname = schemaname) as index_count
        FROM pg_tables
        WHERE schemaname = 'public'
        AND tablename LIKE 'crawl_log_%'
        AND tablename ~ '^crawl_log_[0-9]{4}_[0-9]{2}$'
        ORDER BY partition_month DESC
    """)

    op.execute(
        "COMMENT ON VIEW crawl_log_partitions IS "
        "'Shows all crawl_log partitions with size and metadata'"
    )


def downgrade() -> None:
    """Downgrade schema - convert back to non-partitioned table."""
    op.execute("DROP VIEW IF EXISTS crawl_log_partitions")

    op.execute("DROP FUNCTION IF EXISTS drop_old_crawl_log_partitions(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS create_future_crawl_log_partitions(INTEGER)")
    op.execute("DROP FUNCTION IF EXISTS create_crawl_log_partition(DATE)")

    op.execute("ALTER TABLE crawl_log RENAME TO crawl_log_partitioned")

    op.execute("""
        CREATE TABLE crawl_log (
            id BIGSERIAL PRIMARY KEY,
            job_id UUID NOT NULL REFERENCES crawl_job(id) ON DELETE CASCADE,
            website_id UUID NOT NULL REFERENCES website(id) ON DELETE CASCADE,
            step_name VARCHAR(255),
            log_level log_level_enum NOT NULL DEFAULT 'INFO'::log_level_enum,
            message TEXT NOT NULL,
            context JSONB,
            trace_id UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)

    op.execute("""
        INSERT INTO crawl_log (
            id, job_id, website_id, step_name, log_level,
            message, context, trace_id, created_at
        )
        SELECT
            id, job_id, website_id, step_name, log_level,
            message, context, trace_id, created_at
        FROM crawl_log_partitioned
        ORDER BY created_at
    """)

    op.execute("CREATE INDEX ix_crawl_log_job_id ON crawl_log(job_id)")
    op.execute("CREATE INDEX ix_crawl_log_website_id ON crawl_log(website_id)")
    op.execute("CREATE INDEX ix_crawl_log_log_level ON crawl_log(log_level)")
    op.execute("CREATE INDEX ix_crawl_log_created_at ON crawl_log(created_at)")
    op.execute("CREATE INDEX ix_crawl_log_trace_id ON crawl_log(trace_id)")
    op.execute("CREATE INDEX ix_crawl_log_job_created ON crawl_log(job_id, created_at)")

    op.execute("SELECT setval('crawl_log_id_seq', (SELECT MAX(id) FROM crawl_log))")

    op.execute("DROP TABLE crawl_log_partitioned CASCADE")

    op.execute("COMMENT ON TABLE crawl_log IS 'Stores detailed crawl execution logs'")
