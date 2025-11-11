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
from crawler.utils.simhash import Simhash, compare_texts, find_near_duplicates
from crawler.utils.simhash_helpers import from_signed_int64, to_signed_int64
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
    # Simhash utilities
    "Simhash",
    "compare_texts",
    "find_near_duplicates",
    "to_signed_int64",
    "from_signed_int64",
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
