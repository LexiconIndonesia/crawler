"""add deleted_at to website table

Revision ID: e8f93dc3e336
Revises: af9c85210dfb
Create Date: 2025-11-09 12:34:42.684565

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e8f93dc3e336"
down_revision: str | Sequence[str] | None = "af9c85210dfb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add deleted_at column to website table for soft delete support."""
    op.execute("ALTER TABLE website ADD COLUMN deleted_at TIMESTAMP WITH TIME ZONE DEFAULT NULL")
    op.execute(
        "COMMENT ON COLUMN website.deleted_at IS "
        "'Timestamp when website was soft deleted (NULL = active)'"
    )
    op.execute("CREATE INDEX ix_website_deleted_at ON website(deleted_at) WHERE deleted_at IS NULL")


def downgrade() -> None:
    """Remove deleted_at column from website table."""
    op.execute("DROP INDEX IF EXISTS ix_website_deleted_at")
    op.execute("ALTER TABLE website DROP COLUMN IF EXISTS deleted_at")
