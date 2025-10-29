"""Utilities package."""

from crawler.utils.pagination import (
    PaginationPattern,
    PaginationPatternDetector,
    PaginationStopDetector,
    PaginationURLGenerator,
    PathEmbeddedPattern,
    PathSegmentPattern,
    QueryParamPattern,
    StopCondition,
    TemplatePattern,
)
from crawler.utils.url import (
    are_urls_equivalent,
    hash_url,
    normalize_and_hash,
    normalize_url,
)

__all__ = [
    # URL utilities
    "normalize_url",
    "are_urls_equivalent",
    "hash_url",
    "normalize_and_hash",
    # Pagination utilities
    "PaginationPattern",
    "QueryParamPattern",
    "PathSegmentPattern",
    "PathEmbeddedPattern",
    "TemplatePattern",
    "PaginationPatternDetector",
    "PaginationURLGenerator",
    "PaginationStopDetector",
    "StopCondition",
]
