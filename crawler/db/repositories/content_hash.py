"""Content hash repository using sqlc-generated queries."""

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import content_hash, models
from crawler.utils.simhash_helpers import to_signed_int64

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

    async def upsert_with_simhash(
        self,
        content_hash_value: str,
        first_seen_page_id: str | UUID | None,
        simhash_fingerprint: int,
    ) -> models.ContentHash | None:
        """Insert or update content hash with Simhash fingerprint.

        Args:
            content_hash_value: Content hash string (SHA256)
            first_seen_page_id: Optional ID of first page with this content
            simhash_fingerprint: 64-bit Simhash fingerprint for fuzzy matching

        Returns:
            ContentHash model or None
        """
        return await self._querier.upsert_content_hash_with_simhash(
            content_hash=content_hash_value,
            first_seen_page_id=to_uuid_optional(first_seen_page_id),
            simhash_fingerprint=to_signed_int64(simhash_fingerprint),
        )

    async def get(self, content_hash_value: str) -> models.ContentHash | None:
        """Get content hash record."""
        return await self._querier.get_content_hash(content_hash=content_hash_value)

    async def get_by_fingerprint(self, simhash_fingerprint: int) -> models.ContentHash | None:
        """Get content hash by Simhash fingerprint (exact match).

        Args:
            simhash_fingerprint: 64-bit Simhash fingerprint

        Returns:
            ContentHash model or None
        """
        return await self._querier.get_content_hash_by_fingerprint(
            simhash_fingerprint=to_signed_int64(simhash_fingerprint)
        )

    async def find_similar(
        self,
        target_fingerprint: int,
        max_distance: int = 3,
        exclude_hash: str = "",
        limit: int = 10,
    ) -> list[content_hash.FindSimilarContentRow]:
        """Find content with similar Simhash fingerprints.

        Uses Hamming distance to find near-duplicates. Lower distance means
        more similar content.

        Args:
            target_fingerprint: Target Simhash fingerprint to match against
            max_distance: Maximum Hamming distance (default: 3, roughly 95% similar)
            exclude_hash: Optional content hash to exclude from results
            limit: Maximum number of results (default: 10)

        Returns:
            List of similar content hashes with their Hamming distances

        Example:
            >>> # Find content within 3 bits difference (95%+ similar)
            >>> similar = await repo.find_similar(
            ...     target_fingerprint=12345678901234567,
            ...     max_distance=3,
            ...     exclude_hash="abc123...",
            ...     limit=5
            ... )
            >>> for item in similar:
            ...     print(f"Hash: {item.content_hash}, Distance: {item.hamming_distance}")
        """
        # Collect async generator results into list
        results = []
        async for row in self._querier.find_similar_content(
            target_fingerprint=to_signed_int64(target_fingerprint),
            max_distance=max_distance,
            exclude_hash=exclude_hash,
            limit_count=limit,
        ):
            results.append(row)
        return results
