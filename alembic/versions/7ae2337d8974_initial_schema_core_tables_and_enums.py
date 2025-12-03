"""initial schema - core tables and enums

Revision ID: 7ae2337d8974
Revises:
Create Date: 2025-11-07 22:43:40.582579


Creates:
- Enums: job_type_enum, status_enum, log_level_enum
- Tables: website, crawl_job, crawled_page, content_hash, crawl_log
- Indexes for all tables
- Foreign key constraints

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7ae2337d8974"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema - split into individual statements for asyncpg compatibility."""
    # Create enums
    op.execute("""
        CREATE TYPE job_type_enum AS ENUM (
            'one_time',
            'scheduled',
            'recurring'
        )
    """)

    op.execute("""
        CREATE TYPE status_enum AS ENUM (
            'pending',
            'running',
            'completed',
            'failed',
            'cancelled',
            'active',
            'inactive'
        )
    """)

    op.execute("""
        CREATE TYPE log_level_enum AS ENUM (
            'DEBUG',
            'INFO',
            'WARNING',
            'ERROR',
            'CRITICAL'
        )
    """)

    # Create website table
    op.execute("""
        CREATE TABLE website (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            name VARCHAR(255) NOT NULL UNIQUE,
            base_url VARCHAR(2048) NOT NULL,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            status status_enum NOT NULL DEFAULT 'active'::status_enum,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_by VARCHAR(255)
        )
    """)

    op.execute("COMMENT ON TABLE website IS 'Stores website configurations and metadata'")

    # Website indexes
    op.execute("CREATE INDEX ix_website_status ON website(status)")
    op.execute("CREATE INDEX ix_website_config ON website USING gin(config)")
    op.execute("CREATE INDEX ix_website_created_at ON website(created_at)")

    # Create crawl_job table
    op.execute("""
        CREATE TABLE crawl_job (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            website_id UUID NOT NULL REFERENCES website(id) ON DELETE CASCADE,
            job_type job_type_enum NOT NULL DEFAULT 'one_time'::job_type_enum,
            seed_url VARCHAR(2048) NOT NULL,
            embedded_config JSONB,
            status status_enum NOT NULL DEFAULT 'pending'::status_enum,
            priority INTEGER NOT NULL DEFAULT 5,
            scheduled_at TIMESTAMPTZ,
            started_at TIMESTAMPTZ,
            completed_at TIMESTAMPTZ,
            cancelled_at TIMESTAMPTZ,
            cancelled_by VARCHAR(255),
            cancellation_reason TEXT,
            error_message TEXT,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            metadata JSONB,
            variables JSONB,
            progress JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_crawl_job_valid_priority CHECK (priority >= 1 AND priority <= 10),
            CONSTRAINT ck_crawl_job_valid_retry_count CHECK (retry_count >= 0),
            CONSTRAINT ck_crawl_job_valid_max_retries CHECK (max_retries >= 0)
        )
    """)

    op.execute("COMMENT ON TABLE crawl_job IS 'Stores crawl job definitions and execution state'")

    # Crawl job indexes
    op.execute("CREATE INDEX ix_crawl_job_website_id ON crawl_job(website_id)")
    op.execute("CREATE INDEX ix_crawl_job_job_type ON crawl_job(job_type)")
    op.execute("CREATE INDEX ix_crawl_job_status ON crawl_job(status)")
    op.execute("CREATE INDEX ix_crawl_job_scheduled_at ON crawl_job(scheduled_at)")
    op.execute("CREATE INDEX ix_crawl_job_created_at ON crawl_job(created_at)")
    op.execute("CREATE INDEX ix_crawl_job_seed_url ON crawl_job(seed_url)")
    op.execute("CREATE INDEX ix_crawl_job_priority_status ON crawl_job(priority, status)")

    # Create crawled_page table
    op.execute("""
        CREATE TABLE crawled_page (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
            website_id UUID NOT NULL REFERENCES website(id) ON DELETE CASCADE,
            job_id UUID NOT NULL REFERENCES crawl_job(id) ON DELETE CASCADE,
            url VARCHAR(2048) NOT NULL,
            url_hash VARCHAR(64) NOT NULL,
            content_hash VARCHAR(64) NOT NULL,
            title VARCHAR(500),
            extracted_content TEXT,
            metadata JSONB,
            gcs_html_path VARCHAR(1024),
            gcs_documents JSONB,
            is_duplicate BOOLEAN NOT NULL DEFAULT false,
            duplicate_of UUID REFERENCES crawled_page(id) ON DELETE SET NULL,
            similarity_score INTEGER,
            crawled_at TIMESTAMPTZ NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_crawled_page_valid_similarity_score CHECK (
                similarity_score IS NULL OR
                (similarity_score >= 0 AND similarity_score <= 100)
            )
        )
    """)

    op.execute("COMMENT ON TABLE crawled_page IS 'Stores crawled page data and content'")

    # Crawled page indexes
    op.execute("CREATE INDEX ix_crawled_page_website_id ON crawled_page(website_id)")
    op.execute("CREATE INDEX ix_crawled_page_job_id ON crawled_page(job_id)")
    op.execute("CREATE INDEX ix_crawled_page_url_hash ON crawled_page(url_hash)")
    op.execute("CREATE INDEX ix_crawled_page_content_hash ON crawled_page(content_hash)")
    op.execute("CREATE INDEX ix_crawled_page_crawled_at ON crawled_page(crawled_at)")
    op.execute("CREATE INDEX ix_crawled_page_is_duplicate ON crawled_page(is_duplicate)")
    op.execute("CREATE INDEX ix_crawled_page_duplicate_of ON crawled_page(duplicate_of)")
    op.execute(
        "CREATE UNIQUE INDEX ix_crawled_page_website_url_hash ON crawled_page(website_id, url_hash)"
    )

    # Create content_hash table
    op.execute("""
        CREATE TABLE content_hash (
            content_hash VARCHAR(64) PRIMARY KEY,
            first_seen_page_id UUID REFERENCES crawled_page(id) ON DELETE SET NULL,
            occurrence_count INTEGER NOT NULL DEFAULT 1,
            last_seen_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT ck_content_hash_valid_occurrence_count CHECK (occurrence_count >= 1)
        )
    """)

    op.execute(
        "COMMENT ON TABLE content_hash IS 'Tracks content hash occurrences for duplicate detection'"
    )

    # Content hash indexes
    op.execute("CREATE INDEX ix_content_hash_last_seen_at ON content_hash(last_seen_at)")
    op.execute("CREATE INDEX ix_content_hash_occurrence_count ON content_hash(occurrence_count)")

    # Create crawl_log table
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

    op.execute("COMMENT ON TABLE crawl_log IS 'Stores detailed crawl execution logs'")

    # Crawl log indexes
    op.execute("CREATE INDEX ix_crawl_log_job_id ON crawl_log(job_id)")
    op.execute("CREATE INDEX ix_crawl_log_website_id ON crawl_log(website_id)")
    op.execute("CREATE INDEX ix_crawl_log_log_level ON crawl_log(log_level)")
    op.execute("CREATE INDEX ix_crawl_log_created_at ON crawl_log(created_at)")
    op.execute("CREATE INDEX ix_crawl_log_trace_id ON crawl_log(trace_id)")
    op.execute("CREATE INDEX ix_crawl_log_job_created ON crawl_log(job_id, created_at)")


def downgrade() -> None:
    """Downgrade schema."""
    # Drop tables
    op.execute("DROP TABLE IF EXISTS crawl_log CASCADE")
    op.execute("DROP TABLE IF EXISTS content_hash CASCADE")
    op.execute("DROP TABLE IF EXISTS crawled_page CASCADE")
    op.execute("DROP TABLE IF EXISTS crawl_job CASCADE")
    op.execute("DROP TABLE IF EXISTS website CASCADE")

    # Drop enums
    op.execute("DROP TYPE IF EXISTS log_level_enum")
    op.execute("DROP TYPE IF EXISTS status_enum")
    op.execute("DROP TYPE IF EXISTS job_type_enum")
