-- version: 002
-- description: Add scheduled jobs support with cron schedules
-- requires: PostgreSQL 18+
-- date: 2025-10-27
--
-- This migration adds:
-- 1. cron_schedule field to website table for default schedules
-- 2. scheduled_job table for tracking scheduled crawl jobs
-- 3. Indexes for efficient scheduling queries

-- ============================================================================
-- ALTER EXISTING TABLES
-- ============================================================================

-- Add cron_schedule to website table (default: every 2 weeks on 1st and 15th at midnight)
ALTER TABLE website
ADD COLUMN cron_schedule VARCHAR(255) DEFAULT '0 0 1,15 * *';

COMMENT ON COLUMN website.cron_schedule IS 'Default cron schedule expression for this website (default: "0 0 1,15 * *" runs on 1st and 15th at midnight, approximately every 2 weeks)';


-- ============================================================================
-- CREATE NEW TABLES
-- ============================================================================

-- Scheduled Job table
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
        cron_schedule ~ '^(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+)\s+(\*|[0-9,\-/]+|[A-Z]{3})\s+(\*|[0-9,\-/]+|[A-Z]{3})(\s+(\*|[0-9,\-/]+))?$'
    )
);

COMMENT ON TABLE scheduled_job IS 'Stores scheduled crawl job configurations with cron schedules';
COMMENT ON COLUMN scheduled_job.cron_schedule IS 'Cron expression defining when the job should run';
COMMENT ON COLUMN scheduled_job.next_run_time IS 'Next scheduled execution time';
COMMENT ON COLUMN scheduled_job.last_run_time IS 'Most recent execution time';
COMMENT ON COLUMN scheduled_job.is_active IS 'Flag to pause/resume schedule without deleting';
COMMENT ON COLUMN scheduled_job.job_config IS 'Job-specific configuration overrides';


-- ============================================================================
-- CREATE INDEXES
-- ============================================================================

-- Scheduled Job indexes
CREATE INDEX ix_scheduled_job_website_id ON scheduled_job(website_id);
CREATE INDEX ix_scheduled_job_next_run_time ON scheduled_job(next_run_time);
CREATE INDEX ix_scheduled_job_is_active ON scheduled_job(is_active);
CREATE INDEX ix_scheduled_job_active_next_run ON scheduled_job(is_active, next_run_time)
    WHERE is_active = true;

COMMENT ON INDEX ix_scheduled_job_active_next_run IS 'Optimized index for finding next jobs to execute';
