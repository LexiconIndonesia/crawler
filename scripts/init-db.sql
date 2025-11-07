-- Initialize database for Docker container startup
-- This file is executed when PostgreSQL 18+ container starts
--
-- Note: Minimal initialization only. Full schema is managed via migrations.
-- Run migrations with: make db-migrate

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "pg_trgm";     -- Trigram similarity for text search
CREATE EXTENSION IF NOT EXISTS "btree_gin";   -- GIN indexes for btree types

-- Create migration tracking table (will be overwritten by 000_migration_tracking.sql)
CREATE TABLE IF NOT EXISTS schema_migrations (
    version VARCHAR(255) PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    description TEXT,
    checksum VARCHAR(64)
);

-- Note: UUIDv7 is built-in to PostgreSQL 18+, no extension needed
