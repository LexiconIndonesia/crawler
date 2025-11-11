"""Duplicate content service with business logic."""

from crawler.core.logging import get_logger
from crawler.db.generated.duplicate_group import (
    GetDuplicateGroupStatsRow,
    GetGroupWithCanonicalPageRow,
    ListDuplicatesInGroupRow,
)
from crawler.db.generated.models import DuplicateGroup
from crawler.db.repositories import DuplicateGroupRepository

logger = get_logger(__name__)


class DuplicateService:
    """Service for duplicate content operations with dependency injection."""

    def __init__(self, duplicate_repo: DuplicateGroupRepository):
        """Initialize service with dependencies.

        Args:
            duplicate_repo: Duplicate group repository for database access
        """
        self.duplicate_repo = duplicate_repo

    async def list_duplicate_groups(self, limit: int = 50, offset: int = 0) -> list[DuplicateGroup]:
        """List all duplicate groups with pagination.

        Args:
            limit: Maximum number of groups to return (max 100)
            offset: Number of groups to skip for pagination

        Returns:
            List of duplicate groups

        Raises:
            ValueError: If limit exceeds maximum
        """
        if limit > 100:
            raise ValueError("limit cannot exceed 100")

        logger.info("list_duplicate_groups", limit=limit, offset=offset)
        groups = await self.duplicate_repo.list_all_groups(limit=limit, offset=offset)
        logger.info("duplicate_groups_listed", count=len(groups), limit=limit, offset=offset)
        return groups

    async def get_duplicate_group_details(
        self, group_id: str
    ) -> tuple[GetGroupWithCanonicalPageRow, list[ListDuplicatesInGroupRow]]:
        """Get detailed information about a duplicate group.

        Args:
            group_id: UUID of the duplicate group

        Returns:
            Tuple of (group_with_canonical, list_of_duplicates)

        Raises:
            ValueError: If group not found
        """
        logger.info("get_duplicate_group_details", group_id=group_id)

        # Get group with canonical page info
        group = await self.duplicate_repo.get_group_with_canonical(group_id)
        if group is None:
            raise ValueError(f"Duplicate group '{group_id}' not found")

        # Get all duplicates in the group
        duplicates = await self.duplicate_repo.list_duplicates_in_group(group_id)

        logger.info(
            "duplicate_group_details_retrieved",
            group_id=group_id,
            canonical_url=group.canonical_url,
            duplicate_count=len(duplicates),
        )

        return group, duplicates

    async def get_duplicate_group_stats(self, group_id: str) -> GetDuplicateGroupStatsRow:
        """Get statistics for a duplicate group.

        Args:
            group_id: UUID of the duplicate group

        Returns:
            Statistics including group size, avg similarity, timestamps

        Raises:
            ValueError: If group not found
        """
        logger.info("get_duplicate_group_stats", group_id=group_id)

        stats = await self.duplicate_repo.get_group_stats(group_id)
        if stats is None:
            raise ValueError(f"Duplicate group '{group_id}' not found")

        logger.info(
            "duplicate_group_stats_retrieved",
            group_id=group_id,
            group_size=stats.group_size,
            avg_similarity=stats.avg_similarity,
        )

        return stats
