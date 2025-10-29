"""Content hash repository using sqlc-generated queries."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import content_hash, models

from .base import to_uuid_optional


class ContentHashRepository:
    """Repository for content hash operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = content_hash.AsyncQuerier(connection)

    async def upsert(
        self, content_hash_value: str, first_seen_page_id: str | UUID | None
    ) -> models.ContentHash | None:
        """Insert or update content hash (increments count if exists).

        Args:
            content_hash_value: Content hash string
            first_seen_page_id: Optional ID of first page with this content

        Returns:
            ContentHash model or None
        """
        return await self._querier.upsert_content_hash(
            content_hash=content_hash_value,
            first_seen_page_id=to_uuid_optional(first_seen_page_id),
        )

    async def get(self, content_hash_value: str) -> models.ContentHash | None:
        """Get content hash record."""
        return await self._querier.get_content_hash(content_hash=content_hash_value)
