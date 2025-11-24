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
    # Pagination utilities
    "PaginationPattern",
    "PaginationPatternDetector",
    "PaginationStopDetector",
    "PaginationURLGenerator",
    "PathEmbeddedPattern",
    "PathSegmentPattern",
    "QueryParamPattern",
    # Simhash utilities
    "Simhash",
    "StopCondition",
    "TemplatePattern",
    "are_urls_equivalent",
    "compare_texts",
    "find_near_duplicates",
    "from_signed_int64",
    "hash_url",
    "normalize_and_hash",
    # URL utilities
    "normalize_url",
    "to_signed_int64",
]
