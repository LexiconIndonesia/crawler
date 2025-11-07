-- version: 004
-- description: Convert crawl_log to partitioned table with monthly partitioning and retention policy
-- requires: PostgreSQL 18+
-- date: 2025-11-07
--
-- This migration converts the existing crawl_log table to use native PostgreSQL partitioning
-- with monthly partitions for better performance and automated retention management.
--
-- Benefits:
-- 1. Faster queries on recent data (partition pruning)
-- 2. Easier data retention (drop old partitions instead of DELETE)
-- 3. Better index maintenance (smaller partition-level indexes)
-- 4. Improved vacuum performance

-- ============================================================================
-- STEP 1: Create partitioned table
-- ============================================================================

-- Rename existing table to preserve data
ALTER TABLE crawl_log RENAME TO crawl_log_old;

-- Create new partitioned table with same structure
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
) PARTITION BY RANGE (created_at);

COMMENT ON TABLE crawl_log IS 'Stores detailed crawl execution logs (partitioned by month)';

-- Add foreign key constraints (must be done after table creation)
-- Note: Foreign keys on partitioned tables must include the partition key
ALTER TABLE crawl_log ADD CONSTRAINT fk_crawl_log_job
    FOREIGN KEY (job_id) REFERENCES crawl_job(id) ON DELETE CASCADE NOT VALID;

ALTER TABLE crawl_log ADD CONSTRAINT fk_crawl_log_website
    FOREIGN KEY (website_id) REFERENCES website(id) ON DELETE CASCADE NOT VALID;


-- ============================================================================
-- STEP 2: Create partition management functions
-- ============================================================================

-- Function to create a partition for a given month
CREATE OR REPLACE FUNCTION create_crawl_log_partition(partition_date DATE)
RETURNS TEXT AS $$
DECLARE
    partition_name TEXT;
    start_date DATE;
    end_date DATE;
BEGIN
    -- Calculate partition boundaries (first day of month to first day of next month)
    start_date := DATE_TRUNC('month', partition_date);
    end_date := start_date + INTERVAL '1 month';

    -- Generate partition name: crawl_log_yyyy_mm
    partition_name := 'crawl_log_' || TO_CHAR(start_date, 'YYYY_MM');

    -- Check if partition already exists
    IF EXISTS (
        SELECT 1 FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = partition_name
        AND n.nspname = 'public'
    ) THEN
        RETURN 'Partition ' || partition_name || ' already exists';
    END IF;

    -- Create the partition
    EXECUTE format(
        'CREATE TABLE %I PARTITION OF crawl_log FOR VALUES FROM (%L) TO (%L)',
        partition_name,
        start_date,
        end_date
    );

    -- Create indexes on the partition
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

    RETURN 'Created partition ' || partition_name || ' for range [' ||
           start_date || ', ' || end_date || ')';
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_crawl_log_partition IS 'Creates a monthly partition for crawl_log table with indexes';


-- Function to create partitions for next N months
CREATE OR REPLACE FUNCTION create_future_crawl_log_partitions(months_ahead INTEGER DEFAULT 3)
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
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION create_future_crawl_log_partitions IS 'Creates partitions for the next N months (default: 3)';


-- Function to drop partitions older than retention period
CREATE OR REPLACE FUNCTION drop_old_crawl_log_partitions(retention_days INTEGER DEFAULT 90)
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
        -- Extract date from partition name (crawl_log_YYYY_MM)
        BEGIN
            partition_month := TO_DATE(
                SUBSTRING(partition_record.tablename FROM 'crawl_log_([0-9]{4}_[0-9]{2})'),
                'YYYY_MM'
            );

            IF partition_month < DATE_TRUNC('month', cutoff_date) THEN
                EXECUTE format('DROP TABLE IF EXISTS %I CASCADE', partition_record.tablename);
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
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION drop_old_crawl_log_partitions IS 'Drops log partitions older than retention period (default: 90 days). Returns status, partition_name, message for each partition.';


-- ============================================================================
-- STEP 3: Create initial partitions
-- ============================================================================

-- Create partitions for past 3 months, current month, and next 3 months
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
$$;


-- ============================================================================
-- STEP 4: Migrate data from old table
-- ============================================================================

-- Insert all data from old table to partitioned table
INSERT INTO crawl_log (
    id, job_id, website_id, step_name, log_level,
    message, context, trace_id, created_at
)
SELECT
    id, job_id, website_id, step_name, log_level,
    message, context, trace_id, created_at
FROM crawl_log_old
ORDER BY created_at;

-- Update sequence to continue from the last ID
SELECT setval('crawl_log_id_seq', (SELECT MAX(id) FROM crawl_log));


-- ============================================================================
-- STEP 5: Validate foreign keys
-- ============================================================================

-- Validate foreign keys (this was deferred with NOT VALID)
ALTER TABLE crawl_log VALIDATE CONSTRAINT fk_crawl_log_job;
ALTER TABLE crawl_log VALIDATE CONSTRAINT fk_crawl_log_website;


-- ============================================================================
-- STEP 6: Drop old table
-- ============================================================================

DROP TABLE crawl_log_old CASCADE;


-- ============================================================================
-- STEP 7: Create maintenance view
-- ============================================================================

-- View to monitor partition status
CREATE OR REPLACE VIEW crawl_log_partitions AS
SELECT
    schemaname,
    tablename as partition_name,
    TO_DATE(SUBSTRING(tablename FROM 'crawl_log_([0-9]{4}_[0-9]{2})'), 'YYYY_MM') as partition_month,
    pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
    (SELECT COUNT(*) FROM pg_class c
     JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relname = tablename AND n.nspname = schemaname) as index_count
FROM pg_tables
WHERE schemaname = 'public'
AND tablename LIKE 'crawl_log_%'
AND tablename ~ '^crawl_log_[0-9]{4}_[0-9]{2}$'
ORDER BY partition_month DESC;

COMMENT ON VIEW crawl_log_partitions IS 'Shows all crawl_log partitions with size and metadata';
