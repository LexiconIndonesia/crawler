"""Utilities package."""

from crawler.utils.url import (
    are_urls_equivalent,
    hash_url,
    normalize_and_hash,
    normalize_url,
)

__all__ = ["normalize_url", "are_urls_equivalent", "hash_url", "normalize_and_hash"]
