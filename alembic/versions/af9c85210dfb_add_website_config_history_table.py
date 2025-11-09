"""add website config history table

Revision ID: af9c85210dfb
Revises: 1d3ac885f5c4
Create Date: 2025-11-09 11:54:29.200716

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "af9c85210dfb"
down_revision: str | Sequence[str] | None = "1d3ac885f5c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create table
    op.execute("""
    CREATE TABLE website_config_history (
        id UUID PRIMARY KEY DEFAULT uuidv7(),
        website_id UUID NOT NULL REFERENCES website(id) ON DELETE CASCADE,
        version INTEGER NOT NULL,
        config JSONB NOT NULL,
        changed_by VARCHAR(255),
        change_reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

        CONSTRAINT ck_website_config_history_valid_version CHECK (version >= 1)
    )
    """)

    # Add comments
    op.execute("""
    COMMENT ON TABLE website_config_history IS
        'Stores configuration history for websites to track changes over time'
    """)
    op.execute("""
    COMMENT ON COLUMN website_config_history.version IS
        'Version number, incremented with each change (starts at 1)'
    """)
    op.execute("""
    COMMENT ON COLUMN website_config_history.config IS
        'Full configuration snapshot at this version'
    """)
    op.execute("""
    COMMENT ON COLUMN website_config_history.changed_by IS
        'User or system that made the change'
    """)
    op.execute("""
    COMMENT ON COLUMN website_config_history.change_reason IS
        'Optional description of why the change was made'
    """)

    # Create indexes
    op.execute("""
    CREATE INDEX ix_website_config_history_website_id
        ON website_config_history(website_id)
    """)
    op.execute("""
    CREATE INDEX ix_website_config_history_website_version
        ON website_config_history(website_id, version DESC)
    """)
    op.execute("""
    CREATE UNIQUE INDEX uq_website_config_history_website_version
        ON website_config_history(website_id, version)
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
    DROP TABLE IF EXISTS website_config_history CASCADE;
    """)
