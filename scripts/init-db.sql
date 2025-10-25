-- Initialize database schema
-- This file is executed when PostgreSQL container starts

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Create initial schema (if needed)
-- Tables will be created by Alembic migrations
