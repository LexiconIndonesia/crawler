"""add simhash fingerprint to content hash

Revision ID: 91df2bb4560c
Revises: e8f93dc3e336
Create Date: 2025-11-11 10:30:44.874133

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "91df2bb4560c"
down_revision: str | Sequence[str] | None = "e8f93dc3e336"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # Add simhash_fingerprint column for fuzzy content matching
    op.execute("ALTER TABLE content_hash ADD COLUMN simhash_fingerprint BIGINT")

    # Add comment explaining the column
    op.execute(
        "COMMENT ON COLUMN content_hash.simhash_fingerprint IS "
        "'64-bit Simhash fingerprint for fuzzy duplicate detection'"
    )

    # Create index for fast similarity lookups
    op.execute(
        "CREATE INDEX idx_content_hash_simhash ON content_hash(simhash_fingerprint) "
        "WHERE simhash_fingerprint IS NOT NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    # Drop index first
    op.execute("DROP INDEX IF EXISTS idx_content_hash_simhash")

    # Drop column
    op.execute("ALTER TABLE content_hash DROP COLUMN IF EXISTS simhash_fingerprint")
