"""add duplicate group and relationship tables

Revision ID: c7f64249dfa2
Revises: 91df2bb4560c
Create Date: 2025-11-11 16:03:55.039774

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7f64249dfa2"
down_revision: str | Sequence[str] | None = "91df2bb4560c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create duplicate_group table
    op.execute("""
    CREATE TABLE duplicate_group (
        id UUID PRIMARY KEY DEFAULT uuidv7(),
        canonical_page_id UUID NOT NULL REFERENCES crawled_page(id) ON DELETE CASCADE,
        group_size INT NOT NULL DEFAULT 1 CHECK (group_size >= 1),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    """)

    # Create index on canonical_page_id for lookups
    op.execute("""
    CREATE INDEX ix_duplicate_group_canonical_page_id
    ON duplicate_group(canonical_page_id);
    """)

    # Create duplicate_relationship table
    op.execute("""
    CREATE TABLE duplicate_relationship (
        id BIGSERIAL PRIMARY KEY,
        group_id UUID NOT NULL REFERENCES duplicate_group(id) ON DELETE CASCADE,
        duplicate_page_id UUID NOT NULL REFERENCES crawled_page(id) ON DELETE CASCADE,
        detection_method VARCHAR(20) NOT NULL CHECK (detection_method IN (
            'exact_hash',
            'fuzzy_match',
            'url_match',
            'manual'
        )),
        similarity_score INT CHECK (
            similarity_score IS NULL OR (similarity_score >= 0 AND similarity_score <= 100)
        ),
        confidence_threshold INT CHECK (
            confidence_threshold IS NULL OR confidence_threshold >= 0
        ),
        detected_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        detected_by VARCHAR(255),
        CONSTRAINT unique_duplicate_per_group UNIQUE (group_id, duplicate_page_id)
    );
    """)

    # Create indexes for efficient querying
    op.execute("""
    CREATE INDEX ix_duplicate_relationship_group_id
    ON duplicate_relationship(group_id);
    """)

    op.execute("""
    CREATE INDEX ix_duplicate_relationship_duplicate_page_id
    ON duplicate_relationship(duplicate_page_id);
    """)

    op.execute("""
    CREATE INDEX ix_duplicate_relationship_detection_method
    ON duplicate_relationship(detection_method);
    """)

    # Add trigger to update group_size automatically
    op.execute("""
    CREATE OR REPLACE FUNCTION update_duplicate_group_size()
    RETURNS TRIGGER AS $$
    BEGIN
        IF TG_OP = 'INSERT' THEN
            UPDATE duplicate_group
            SET group_size = group_size + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = NEW.group_id;
        ELSIF TG_OP = 'DELETE' THEN
            UPDATE duplicate_group
            SET group_size = group_size - 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = OLD.group_id;
        END IF;
        RETURN NULL;
    END;
    $$ LANGUAGE plpgsql;
    """)

    op.execute("""
    CREATE TRIGGER trigger_update_duplicate_group_size
    AFTER INSERT OR DELETE ON duplicate_relationship
    FOR EACH ROW
    EXECUTE FUNCTION update_duplicate_group_size();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop trigger first
    op.execute(
        "DROP TRIGGER IF EXISTS trigger_update_duplicate_group_size ON duplicate_relationship;"
    )
    op.execute("DROP FUNCTION IF EXISTS update_duplicate_group_size();")

    # Drop indexes
    op.execute("DROP INDEX IF EXISTS ix_duplicate_relationship_detection_method;")
    op.execute("DROP INDEX IF EXISTS ix_duplicate_relationship_duplicate_page_id;")
    op.execute("DROP INDEX IF EXISTS ix_duplicate_relationship_group_id;")
    op.execute("DROP INDEX IF EXISTS ix_duplicate_group_canonical_page_id;")

    # Drop tables (CASCADE will handle foreign keys)
    op.execute("DROP TABLE IF EXISTS duplicate_relationship CASCADE;")
    op.execute("DROP TABLE IF EXISTS duplicate_group CASCADE;")
