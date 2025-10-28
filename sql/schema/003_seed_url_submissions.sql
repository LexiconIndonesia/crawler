-- version: 003
-- description: Extend crawl_job to support seed URL submissions with template reference or inline config
-- requires: PostgreSQL 18+
-- date: 2025-10-28
--
-- This migration adds support for flexible job creation:
-- 1. Jobs can reference a website template (website_id NOT NULL)
-- 2. Jobs can use inline config without a template (website_id NULL, inline_config provided)
--
-- Changes:
-- - Make website_id nullable to support inline configurations
-- - Rename embedded_config to inline_config for clarity
-- - Add validation constraint to ensure either website_id or inline_config is present

-- Make website_id nullable to support inline configurations
ALTER TABLE crawl_job
    ALTER COLUMN website_id DROP NOT NULL;

-- Rename embedded_config to inline_config for better clarity
ALTER TABLE crawl_job
    RENAME COLUMN embedded_config TO inline_config;

-- Add check constraint: either website_id or inline_config must be present
-- This ensures jobs always have configuration (either from website template or inline)
ALTER TABLE crawl_job
    ADD CONSTRAINT ck_crawl_job_config_source CHECK (
        (website_id IS NOT NULL) OR (inline_config IS NOT NULL)
    );

-- Add index on inline_config for queries that filter by configuration
CREATE INDEX ix_crawl_job_inline_config ON crawl_job USING gin(inline_config)
    WHERE inline_config IS NOT NULL;

-- Add partial index for jobs without website_id (inline config jobs)
CREATE INDEX ix_crawl_job_null_website_id ON crawl_job(id)
    WHERE website_id IS NULL;

COMMENT ON COLUMN crawl_job.website_id IS 'Reference to website template (nullable for inline config jobs)';
COMMENT ON COLUMN crawl_job.inline_config IS 'Inline configuration for jobs without website template';
COMMENT ON CONSTRAINT ck_crawl_job_config_source ON crawl_job IS 'Ensures job has either website_id or inline_config';
