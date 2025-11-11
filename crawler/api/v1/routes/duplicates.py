"""Duplicate content management routes for API v1."""

from fastapi import APIRouter, Query, status

from crawler.api.generated import ErrorResponse
from crawler.api.v1.dependencies import DuplicateServiceDep
from crawler.api.v1.handlers import (
    get_duplicate_group_details_handler,
    get_duplicate_group_stats_handler,
    list_duplicate_groups_handler,
)
from crawler.api.v1.models import DuplicateGroupDetails, DuplicateGroupStats, DuplicatePageInfo
from crawler.db.generated.models import DuplicateGroup

router = APIRouter()


@router.get(
    "/groups",
    response_model=list[DuplicateGroup],
    status_code=status.HTTP_200_OK,
    summary="List all duplicate groups",
    operation_id="listDuplicateGroups",
    description="""
    List all duplicate content groups with pagination.

    This endpoint:
    1. Returns all groups where content duplicates have been detected
    2. Supports pagination via limit/offset parameters
    3. Each group represents a cluster of duplicate pages

    **Use cases:**
    - Content audit dashboards showing duplicate statistics
    - Batch processing of duplicate groups
    - Monitoring content quality across crawled websites

    **Pagination:**
    - Default limit: 50 groups
    - Maximum limit: 100 groups
    - Use offset for page navigation
    """,
    responses={
        200: {"description": "List of duplicate groups retrieved successfully"},
        400: {
            "description": "Validation error (e.g., limit exceeds maximum)",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def list_duplicate_groups(
    duplicate_service: DuplicateServiceDep,
    limit: int = Query(50, ge=1, le=100, description="Number of groups to return"),
    offset: int = Query(0, ge=0, description="Number of groups to skip"),
) -> list[DuplicateGroup]:
    """List all duplicate groups with pagination.

    Args:
        duplicate_service: Injected duplicate service
        limit: Maximum number of groups to return (1-100)
        offset: Number of groups to skip for pagination

    Returns:
        List of duplicate groups

    Raises:
        HTTPException 400: If validation fails
        HTTPException 500: If database operation fails
    """
    return await list_duplicate_groups_handler(duplicate_service, limit, offset)


@router.get(
    "/groups/{group_id}",
    response_model=DuplicateGroupDetails,
    status_code=status.HTTP_200_OK,
    summary="Get detailed information about a duplicate group",
    operation_id="getDuplicateGroupDetails",
    description="""
    Retrieve complete details about a specific duplicate group.

    This endpoint:
    1. Returns the canonical (original) page information
    2. Lists all duplicate pages in the group with detection metadata
    3. Includes similarity scores and detection methods

    **Response includes:**
    - Canonical page URL, content hash, and crawl timestamp
    - Complete list of duplicate pages with:
      - Detection method (exact_hash, fuzzy_match, url_match, manual)
      - Similarity percentage (0-100)
      - Detection timestamp and source
      - Original crawl timestamp

    **Use cases:**
    - Investigating specific duplicate clusters
    - Manual review of automatic duplicate detection
    - Content deduplication workflows
    """,
    responses={
        200: {"description": "Group details retrieved successfully"},
        404: {
            "description": "Group not found",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def get_duplicate_group_details(
    group_id: str,
    duplicate_service: DuplicateServiceDep,
) -> DuplicateGroupDetails:
    """Get detailed information about a duplicate group.

    Args:
        group_id: UUID of the duplicate group
        duplicate_service: Injected duplicate service

    Returns:
        Group details including canonical page and all duplicates

    Raises:
        HTTPException 404: If group not found
        HTTPException 500: If database operation fails
    """
    group, duplicates = await get_duplicate_group_details_handler(group_id, duplicate_service)

    # Convert to response model
    return DuplicateGroupDetails(
        id=group.id,
        canonical_page_id=group.canonical_page_id,
        canonical_url=group.canonical_url,
        canonical_content_hash=group.canonical_content_hash,
        canonical_crawled_at=group.canonical_crawled_at,
        group_size=group.group_size,
        created_at=group.created_at,
        updated_at=group.updated_at,
        duplicates=[
            DuplicatePageInfo(
                id=dup.id,
                duplicate_page_id=dup.duplicate_page_id,
                url=dup.url,
                content_hash=dup.content_hash,
                detection_method=dup.detection_method,
                similarity_score=dup.similarity_score,
                confidence_threshold=dup.confidence_threshold,
                detected_at=dup.detected_at,
                detected_by=dup.detected_by,
                crawled_at=dup.crawled_at,
            )
            for dup in duplicates
        ],
    )


@router.get(
    "/groups/{group_id}/stats",
    response_model=DuplicateGroupStats,
    status_code=status.HTTP_200_OK,
    summary="Get statistics for a duplicate group",
    operation_id="getDuplicateGroupStats",
    description="""
    Retrieve aggregated statistics for a duplicate group.

    This endpoint:
    1. Returns group size and relationship counts
    2. Calculates average similarity across all duplicates
    3. Provides detection timestamps (first/last)

    **Statistics included:**
    - Group size (total pages including canonical)
    - Relationship count (number of duplicate links)
    - Average similarity score
    - First/last detection timestamps

    **Use cases:**
    - Duplicate detection quality analysis
    - Performance monitoring dashboards
    - Duplicate trend analysis over time
    """,
    responses={
        200: {"description": "Statistics retrieved successfully"},
        404: {
            "description": "Group not found",
            "model": ErrorResponse,
        },
        500: {
            "description": "Internal server error",
            "model": ErrorResponse,
        },
    },
)
async def get_duplicate_group_stats(
    group_id: str,
    duplicate_service: DuplicateServiceDep,
) -> DuplicateGroupStats:
    """Get statistics for a duplicate group.

    Args:
        group_id: UUID of the duplicate group
        duplicate_service: Injected duplicate service

    Returns:
        Group statistics including averages and timestamps

    Raises:
        HTTPException 404: If group not found
        HTTPException 500: If database operation fails
    """
    stats = await get_duplicate_group_stats_handler(group_id, duplicate_service)

    return DuplicateGroupStats(
        id=stats.id,
        canonical_page_id=stats.canonical_page_id,
        group_size=stats.group_size,
        relationship_count=stats.relationship_count,
        avg_similarity=stats.avg_similarity,
        first_detected=stats.first_detected,
        last_detected=stats.last_detected,
    )
