-- Migration tracking table
-- This must be created first before any other migrations

CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    checksum VARCHAR(64)  -- SHA256 of the migration file for integrity
);

COMMENT ON TABLE schema_migrations IS 'Tracks applied database migrations';
