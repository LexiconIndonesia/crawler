"""Repository for duplicate group operations."""

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import duplicate_group as queries
from crawler.db.generated.duplicate_group import (
    CountDuplicatesByMethodRow,
    GetDuplicateGroupStatsRow,
    GetGroupWithCanonicalPageRow,
    ListDuplicatesInGroupRow,
)
from crawler.db.generated.models import (
    CrawledPage,
    DuplicateGroup,
    DuplicateRelationship,
)
from crawler.db.repositories.base import to_uuid


class DuplicateGroupRepository:
    """Repository for managing duplicate groups and relationships."""

    def __init__(self, conn: AsyncConnection):
        """Initialize repository with database connection.

        Args:
            conn: SQLAlchemy async connection
        """
        self.conn = conn
        self._querier = queries.AsyncQuerier(conn)

    async def create_group(self, canonical_page_id: str) -> DuplicateGroup:
        """Create a new duplicate group.

        Args:
            canonical_page_id: UUID of the canonical (original) page

        Returns:
            DuplicateGroup model

        Example:
            >>> group = await repo.create_group(page_id)
        """
        result = await self._querier.create_duplicate_group(
            canonical_page_id=to_uuid(canonical_page_id)
        )
        assert result is not None, "create_duplicate_group should never return None"
        return result

    async def get_group(self, group_id: str) -> DuplicateGroup | None:
        """Get a duplicate group by ID.

        Args:
            group_id: UUID of the group

        Returns:
            DuplicateGroup model or None if not found
        """
        return await self._querier.get_duplicate_group(id=to_uuid(group_id))

    async def get_group_by_canonical_page(self, canonical_page_id: str) -> DuplicateGroup | None:
        """Get duplicate group for a canonical page.

        Args:
            canonical_page_id: UUID of the canonical page

        Returns:
            DuplicateGroup model or None if not found
        """
        return await self._querier.get_duplicate_group_by_canonical_page(
            canonical_page_id=to_uuid(canonical_page_id)
        )

    async def add_duplicate(
        self,
        group_id: str,
        duplicate_page_id: str,
        detection_method: str,
        similarity_score: int | None = None,
        confidence_threshold: int | None = None,
        detected_by: str | None = None,
    ) -> DuplicateRelationship:
        """Add a page as a duplicate to a group.

        Args:
            group_id: UUID of the duplicate group
            duplicate_page_id: UUID of the duplicate page
            detection_method: Method used ('exact_hash', 'fuzzy_match', 'url_match', 'manual')
            similarity_score: Similarity percentage (0-100), None for exact matches
            confidence_threshold: Threshold used (e.g., Hamming distance for fuzzy match)
            detected_by: Identifier of the detector (e.g., 'scrape_executor', 'manual:username')

        Returns:
            DuplicateRelationship model

        Raises:
            ValueError: If detection_method is invalid or duplicate already exists

        Example:
            >>> rel = await repo.add_duplicate(
            ...     group_id=group.id,
            ...     duplicate_page_id=page_id,
            ...     detection_method='fuzzy_match',
            ...     similarity_score=95,
            ...     confidence_threshold=3,
            ...     detected_by='scrape_executor'
            ... )
        """
        valid_methods = {"exact_hash", "fuzzy_match", "url_match", "manual"}
        if detection_method not in valid_methods:
            raise ValueError(
                f"Invalid detection_method '{detection_method}'. "
                f"Must be one of: {', '.join(sorted(valid_methods))}"
            )

        result = await self._querier.add_duplicate_relationship(
            group_id=to_uuid(group_id),
            duplicate_page_id=to_uuid(duplicate_page_id),
            detection_method=detection_method,
            similarity_score=similarity_score,
            confidence_threshold=confidence_threshold,
            detected_by=detected_by,
        )
        assert result is not None, "add_duplicate_relationship should never return None"
        return result

    async def get_relationship(self, relationship_id: int) -> DuplicateRelationship | None:
        """Get a specific duplicate relationship.

        Args:
            relationship_id: ID of the relationship

        Returns:
            DuplicateRelationship model or None if not found
        """
        return await self._querier.get_duplicate_relationship(id=relationship_id)

    async def get_relationship_by_page(
        self, group_id: str, duplicate_page_id: str
    ) -> DuplicateRelationship | None:
        """Check if a page is already in a group.

        Args:
            group_id: UUID of the group
            duplicate_page_id: UUID of the page to check

        Returns:
            DuplicateRelationship if exists, None otherwise
        """
        return await self._querier.get_duplicate_relationship_by_page(
            group_id=to_uuid(group_id), duplicate_page_id=to_uuid(duplicate_page_id)
        )

    async def list_duplicates_in_group(self, group_id: str) -> list[ListDuplicatesInGroupRow]:
        """List all duplicates in a group with page details.

        Args:
            group_id: UUID of the group

        Returns:
            List of duplicate relationships with page info
        """
        results = []
        async for row in self._querier.list_duplicates_in_group(group_id=to_uuid(group_id)):
            results.append(row)
        return results

    async def find_group_for_page(self, page_id: str) -> DuplicateGroup | None:
        """Find which duplicate group a page belongs to.

        Args:
            page_id: UUID of the page

        Returns:
            DuplicateGroup if page is a duplicate, None otherwise
        """
        return await self._querier.find_duplicate_group_for_page(duplicate_page_id=to_uuid(page_id))

    async def get_group_with_canonical(self, group_id: str) -> GetGroupWithCanonicalPageRow | None:
        """Get group info with canonical page details.

        Args:
            group_id: UUID of the group

        Returns:
            Group with canonical page info or None
        """
        return await self._querier.get_group_with_canonical_page(id=to_uuid(group_id))

    async def list_all_groups(self, limit: int = 50, offset: int = 0) -> list[DuplicateGroup]:
        """List all duplicate groups with pagination.

        Args:
            limit: Maximum number of groups to return
            offset: Number of groups to skip

        Returns:
            List of DuplicateGroup models
        """
        results = []
        async for row in self._querier.list_all_duplicate_groups(limit=limit, offset=offset):
            results.append(row)
        return results

    async def get_group_stats(self, group_id: str) -> GetDuplicateGroupStatsRow | None:
        """Get statistics for a duplicate group.

        Args:
            group_id: UUID of the group

        Returns:
            Statistics including avg similarity, count, timestamps
        """
        return await self._querier.get_duplicate_group_stats(id=to_uuid(group_id))

    async def remove_relationship(self, relationship_id: int) -> None:
        """Remove a duplicate relationship.

        Note: This will trigger automatic group_size update via database trigger.

        Args:
            relationship_id: ID of the relationship to remove
        """
        await self._querier.remove_duplicate_relationship(id=relationship_id)

    async def remove_group(self, group_id: str) -> None:
        """Remove an entire duplicate group.

        Note: CASCADE will remove all relationships in this group.

        Args:
            group_id: UUID of the group to remove
        """
        await self._querier.remove_duplicate_group(id=to_uuid(group_id))

    async def update_similarity_score(
        self, relationship_id: int, similarity_score: int
    ) -> DuplicateRelationship:
        """Update the similarity score for a duplicate relationship.

        Args:
            relationship_id: ID of the relationship
            similarity_score: New similarity score (0-100)

        Returns:
            Updated DuplicateRelationship model

        Raises:
            ValueError: If similarity_score is out of range
        """
        if not (0 <= similarity_score <= 100):
            raise ValueError(f"similarity_score must be 0-100, got {similarity_score}")

        result = await self._querier.update_duplicate_similarity_score(
            id=relationship_id, similarity_score=similarity_score
        )
        assert result is not None, "update_duplicate_similarity_score should never return None"
        return result

    async def count_by_detection_method(self) -> list[CountDuplicatesByMethodRow]:
        """Count duplicates grouped by detection method.

        Returns:
            List of (detection_method, count) tuples
        """
        results = []
        async for row in self._querier.count_duplicates_by_method():
            results.append(row)
        return results

    async def find_orphaned_duplicates(
        self, limit: int = 100, offset: int = 0
    ) -> list[CrawledPage]:
        """Find pages marked as is_duplicate but not in any duplicate_group.

        Useful for migration or fixing inconsistent data.

        Args:
            limit: Maximum pages to return
            offset: Number of pages to skip

        Returns:
            List of CrawledPage models
        """
        results = []
        async for row in self._querier.find_pages_without_duplicate_group(
            limit=limit, offset=offset
        ):
            results.append(row)
        return results

    async def get_canonical_for_duplicate(self, duplicate_page_id: str) -> CrawledPage | None:
        """Get the canonical (original) page for a duplicate.

        Args:
            duplicate_page_id: UUID of the duplicate page

        Returns:
            CrawledPage model of the canonical page or None

        Example:
            >>> canonical = await repo.get_canonical_for_duplicate(dup_page_id)
            >>> print(f"Original: {canonical.url}")
        """
        return await self._querier.get_canonical_page_for_duplicate(
            duplicate_page_id=to_uuid(duplicate_page_id)
        )
