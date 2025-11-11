"""Duplicate content request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from crawler.api.v1.decorators import handle_service_errors
from crawler.api.v1.services import DuplicateService
from crawler.core.logging import get_logger
from crawler.db.generated.duplicate_group import (
    GetDuplicateGroupStatsRow,
    GetGroupWithCanonicalPageRow,
    ListDuplicatesInGroupRow,
)
from crawler.db.generated.models import DuplicateGroup

logger = get_logger(__name__)


@handle_service_errors(operation="listing duplicate groups")
async def list_duplicate_groups_handler(
    duplicate_service: DuplicateService,
    limit: int = 50,
    offset: int = 0,
) -> list[DuplicateGroup]:
    """Handle listing duplicate groups with HTTP error translation.

    Args:
        duplicate_service: Injected duplicate service
        limit: Maximum number of groups to return
        offset: Number of groups to skip for pagination

    Returns:
        List of duplicate groups

    Raises:
        HTTPException: If validation fails or operation fails (via decorator)
    """
    logger.info("list_duplicate_groups_request", limit=limit, offset=offset)
    return await duplicate_service.list_duplicate_groups(limit=limit, offset=offset)


@handle_service_errors(operation="retrieving duplicate group details")
async def get_duplicate_group_details_handler(
    group_id: str,
    duplicate_service: DuplicateService,
) -> tuple[GetGroupWithCanonicalPageRow, list[ListDuplicatesInGroupRow]]:
    """Handle duplicate group details retrieval with HTTP error translation.

    Args:
        group_id: UUID of the duplicate group
        duplicate_service: Injected duplicate service

    Returns:
        Tuple of (group_with_canonical, list_of_duplicates)

    Raises:
        HTTPException: If group not found or operation fails (via decorator)
    """
    logger.info("get_duplicate_group_details_request", group_id=group_id)
    return await duplicate_service.get_duplicate_group_details(group_id)


@handle_service_errors(operation="retrieving duplicate group statistics")
async def get_duplicate_group_stats_handler(
    group_id: str,
    duplicate_service: DuplicateService,
) -> GetDuplicateGroupStatsRow:
    """Handle duplicate group statistics retrieval with HTTP error translation.

    Args:
        group_id: UUID of the duplicate group
        duplicate_service: Injected duplicate service

    Returns:
        Statistics including group size, avg similarity, timestamps

    Raises:
        HTTPException: If group not found or operation fails (via decorator)
    """
    logger.info("get_duplicate_group_stats_request", group_id=group_id)
    return await duplicate_service.get_duplicate_group_stats(group_id)
