"""Pagination detection and URL generation utilities.

This module provides intelligent pagination handling by:
1. Detecting pagination patterns from seed URLs (query params, path segments, templates)
2. Generating next page URLs without DOM parsing
3. Detecting stop conditions (404, duplicates, empty responses)
4. Supporting circular pagination detection via content hashing

Example:
    >>> # Seed URL: https://example.com/products?page=5
    >>> detector = PaginationPatternDetector()
    >>> pattern = detector.detect("https://example.com/products?page=5")
    >>> pattern.current_page
    5
    >>> pattern.generate_url("https://example.com/products?page=5", 6)
    'https://example.com/products?page=6'
"""

import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from crawler.core.logging import get_logger

logger = get_logger(__name__)


# =============================================================================
# Pagination Pattern Classes
# =============================================================================


@dataclass
class PaginationPattern(ABC):
    """Abstract base class for pagination patterns."""

    current_page: int

    @abstractmethod
    def generate_url(self, base_url: str, page_number: int) -> str:
        """Generate URL for a specific page number.

        Args:
            base_url: The original seed URL
            page_number: Target page number to generate

        Returns:
            Generated URL for the target page
        """
        pass


@dataclass
class QueryParamPattern(PaginationPattern):
    """Pagination via query parameter (e.g., ?page=5, ?offset=20).

    Examples:
        - https://example.com/products?page=5
        - https://example.com/search?q=test&page=2&sort=date
        - https://example.com/api/items?offset=40&limit=20
    """

    param_name: str  # e.g., "page", "p", "offset"
    increment: int = 1  # For offset-based: increment by page size (e.g., 20)

    def generate_url(self, base_url: str, page_number: int) -> str:
        """Generate URL with updated query parameter."""
        parsed = urlparse(base_url)
        params = parse_qs(parsed.query, keep_blank_values=True)

        # Update page parameter
        if self.param_name == "offset":
            # Offset-based: calculate offset from page number
            params[self.param_name] = [str((page_number - 1) * self.increment)]
        else:
            # Page-based: direct page number
            params[self.param_name] = [str(page_number)]

        # Flatten params (parse_qs returns lists)
        params_dict = {k: v[0] if isinstance(v, list) else v for k, v in params.items()}
        new_query = urlencode(params_dict)

        return urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment)
        )


@dataclass
class PathSegmentPattern(PaginationPattern):
    """Pagination via path segment (e.g., /page/5, /products/page/3).

    Examples:
        - https://example.com/page/5
        - https://example.com/products/page/3
        - https://example.com/category/electronics/p/2
    """

    segment_index: int  # Position in path where page number appears

    def generate_url(self, base_url: str, page_number: int) -> str:
        """Generate URL with updated path segment."""
        parsed = urlparse(base_url)
        path_parts = parsed.path.split("/")

        # Update the page number at the specific index
        if 0 <= self.segment_index < len(path_parts):
            path_parts[self.segment_index] = str(page_number)

        new_path = "/".join(path_parts)

        return urlunparse(
            (parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment)
        )


@dataclass
class PathEmbeddedPattern(PaginationPattern):
    """Pagination embedded in path (e.g., /products-p5, /list5.html).

    Examples:
        - https://example.com/products-p5
        - https://example.com/category/list5.html
        - https://example.com/archive2024-page3
    """

    prefix: str  # Everything before the page number
    suffix: str  # Everything after the page number (e.g., ".html")

    def generate_url(self, base_url: str, page_number: int) -> str:
        """Generate URL with embedded page number in path."""
        parsed = urlparse(base_url)

        # Reconstruct path with new page number
        new_path = f"{self.prefix}{page_number}{self.suffix}"

        return urlunparse(
            (parsed.scheme, parsed.netloc, new_path, parsed.params, parsed.query, parsed.fragment)
        )


@dataclass
class TemplatePattern(PaginationPattern):
    """Pagination via URL template (e.g., https://example.com/page/{page}).

    This is used when the user provides an explicit template in the config.

    Examples:
        - https://example.com/page/{page}
        - https://example.com/products?page={page}&sort=date
        - https://example.com/category/{category}/page/{page}
    """

    current_page: int  # Current page number
    template: str  # URL template with {page} placeholder

    def generate_url(self, base_url: str, page_number: int) -> str:
        """Generate URL from template by replacing {page} placeholder.

        Note: base_url is ignored since template is self-contained.
        """
        _ = base_url  # Template-based patterns don't use base_url
        return self.template.replace("{page}", str(page_number))


# =============================================================================
# Pattern Detection
# =============================================================================


class PaginationPatternDetector:
    """Detect pagination pattern from seed URL.

    This class analyzes a seed URL to automatically detect the pagination pattern
    being used, without requiring explicit configuration.

    Detection strategies (in order):
    1. Query parameters (page, p, offset, start, skip, from)
    2. Path segments (/page/5, /p/5)
    3. Embedded numbers in path (/products-p5, /list5.html)

    Example:
        >>> detector = PaginationPatternDetector()
        >>> pattern = detector.detect("https://example.com/products?page=5")
        >>> isinstance(pattern, QueryParamPattern)
        True
        >>> pattern.current_page
        5
    """

    # Common pagination parameter names (in priority order)
    QUERY_PARAM_NAMES = ["page", "p", "offset", "start", "skip", "from"]

    # Common path segment indicators
    PATH_SEGMENT_INDICATORS = ["page", "p"]

    def detect(self, seed_url: str) -> PaginationPattern | None:
        """Detect pagination pattern from seed URL.

        Args:
            seed_url: The seed URL to analyze

        Returns:
            Detected pagination pattern or None if no pattern found

        Raises:
            ValueError: If URL is invalid
        """
        if not seed_url or not isinstance(seed_url, str):
            raise ValueError("seed_url must be a non-empty string")

        try:
            parsed = urlparse(seed_url.strip())
        except Exception as e:
            raise ValueError(f"Invalid URL: {e}") from e

        if not parsed.scheme or not parsed.netloc:
            raise ValueError(f"URL must have scheme and hostname: {seed_url}")

        # Strategy 1: Check query parameters
        pattern = self._detect_query_param(parsed)
        if pattern:
            logger.info(
                "pagination_pattern_detected",
                type="query_param",
                param_name=pattern.param_name,
                current_page=pattern.current_page,
            )
            return pattern

        # Strategy 2: Check path segments
        pattern = self._detect_path_segment(parsed)
        if pattern:
            logger.info(
                "pagination_pattern_detected",
                type="path_segment",
                segment_index=pattern.segment_index,
                current_page=pattern.current_page,
            )
            return pattern

        # Strategy 3: Check embedded numbers in path
        pattern = self._detect_path_embedded(parsed)
        if pattern:
            logger.info(
                "pagination_pattern_detected",
                type="path_embedded",
                prefix=pattern.prefix,
                suffix=pattern.suffix,
                current_page=pattern.current_page,
            )
            return pattern

        logger.warning("pagination_pattern_not_detected", url=seed_url)
        return None

    def _detect_query_param(self, parsed: Any) -> QueryParamPattern | None:
        """Detect query parameter pagination pattern."""
        if not parsed.query:
            return None

        params = parse_qs(parsed.query)

        # Check for common pagination parameters
        for param_name in self.QUERY_PARAM_NAMES:
            if param_name in params:
                try:
                    value = int(params[param_name][0])

                    # Determine increment for offset-based pagination
                    increment = 1
                    if param_name == "offset":
                        # Try to infer page size from 'limit' or 'size' param
                        if "limit" in params:
                            increment = int(params["limit"][0])
                        elif "size" in params:
                            increment = int(params["size"][0])
                        else:
                            increment = 20  # Default offset increment

                        # Convert offset to page number (1-indexed)
                        current_page = (value // increment) + 1
                    else:
                        current_page = value

                    return QueryParamPattern(
                        param_name=param_name,
                        current_page=current_page,
                        increment=increment,
                    )
                except (ValueError, IndexError):
                    continue

        return None

    def _detect_path_segment(self, parsed: Any) -> PathSegmentPattern | None:
        """Detect path segment pagination pattern."""
        if not parsed.path:
            return None

        path_parts = parsed.path.split("/")

        # Look for indicators like /page/5 or /p/3
        for i, part in enumerate(path_parts):
            if part.lower() in self.PATH_SEGMENT_INDICATORS:
                # Check if next segment is a number
                if i + 1 < len(path_parts):
                    try:
                        page_number = int(path_parts[i + 1])
                        return PathSegmentPattern(
                            segment_index=i + 1,
                            current_page=page_number,
                        )
                    except ValueError:
                        continue

        return None

    def _detect_path_embedded(self, parsed: Any) -> PathEmbeddedPattern | None:
        """Detect embedded number pagination pattern in path."""
        if not parsed.path:
            return None

        # Look for patterns like /products-p5, /list5.html, /archive2024-page3
        # Match: (non-digits)(digits)(optional non-digits)
        match = re.search(r"^(.*\D)(\d+)(\D*)$", parsed.path)
        if match:
            try:
                page_number = int(match.group(2))
                # Only consider it pagination if number is reasonable (1-9999)
                if 1 <= page_number <= 9999:
                    return PathEmbeddedPattern(
                        prefix=match.group(1),
                        current_page=page_number,
                        suffix=match.group(3),
                    )
            except ValueError:
                pass

        return None


# =============================================================================
# URL Generation
# =============================================================================


class PaginationURLGenerator:
    """Generate pagination URLs based on detected or configured pattern.

    Example:
        >>> pattern = QueryParamPattern(param_name="page", current_page=5)
        >>> generator = PaginationURLGenerator("https://example.com?page=5", pattern)
        >>> generator.next_url()
        'https://example.com?page=6'
        >>> generator.generate_range(5, 10)
        ['https://example.com?page=5', ..., 'https://example.com?page=10']
    """

    def __init__(self, seed_url: str, pattern: PaginationPattern, max_pages: int = 100):
        """Initialize URL generator.

        Args:
            seed_url: The original seed URL
            pattern: Detected pagination pattern
            max_pages: Maximum number of pages to generate
        """
        self.seed_url = seed_url
        self.pattern = pattern
        self.max_pages = max_pages
        self.current_page = pattern.current_page

    def next_url(self) -> str | None:
        """Generate the next page URL.

        Returns:
            Next page URL or None if max_pages reached
        """
        next_page = self.current_page + 1
        if next_page > self.max_pages:
            return None

        self.current_page = next_page
        return self.pattern.generate_url(self.seed_url, next_page)

    def generate_range(
        self, start_page: int | None = None, end_page: int | None = None
    ) -> list[str]:
        """Generate URLs for a range of pages.

        Args:
            start_page: Starting page (default: current_page + 1)
            end_page: Ending page (default: max_pages)

        Returns:
            List of generated URLs
        """
        start = start_page if start_page is not None else self.current_page + 1
        end = min(end_page if end_page is not None else self.max_pages, self.max_pages)

        return [self.pattern.generate_url(self.seed_url, page) for page in range(start, end + 1)]

    def generate_all(self) -> list[str]:
        """Generate all remaining page URLs up to max_pages.

        Returns:
            List of all remaining URLs
        """
        return self.generate_range(self.current_page + 1, self.max_pages)


# =============================================================================
# Stop Condition Detection
# =============================================================================


@dataclass
class StopCondition:
    """Result of stop condition check."""

    should_stop: bool
    reason: str


class PaginationStopDetector:
    """Detect when pagination should stop.

    Tracks:
    - HTTP error responses (404, 5xx)
    - Empty responses
    - Duplicate content (via content hashing)
    - Circular pagination (URL revisits)

    Example:
        >>> detector = PaginationStopDetector()
        >>> result = detector.check_response(404, b"", "https://example.com/page/100")
        >>> result.should_stop
        True
        >>> result.reason
        '404 Not Found'
    """

    def __init__(
        self,
        min_content_length: int = 100,
        max_empty_responses: int = 2,
        track_content_hashes: bool = True,
        track_urls: bool = True,
    ):
        """Initialize stop detector.

        Args:
            min_content_length: Minimum content length to consider non-empty
            max_empty_responses: Max consecutive empty responses before stopping
            track_content_hashes: Enable duplicate content detection
            track_urls: Enable URL revisit detection
        """
        self.min_content_length = min_content_length
        self.max_empty_responses = max_empty_responses
        self.track_content_hashes = track_content_hashes
        self.track_urls = track_urls

        self.visited_hashes: set[str] = set()
        self.visited_urls: set[str] = set()
        self.consecutive_empty = 0

    def check_response(self, status_code: int, content: bytes | str, url: str) -> StopCondition:
        """Check if pagination should stop based on response.

        Args:
            status_code: HTTP status code
            content: Response content (bytes or string)
            url: Current page URL

        Returns:
            StopCondition with should_stop flag and reason
        """
        # Check HTTP errors
        if status_code == 404:
            return StopCondition(True, "404 Not Found - end of pagination")

        if status_code == 403:
            return StopCondition(True, "403 Forbidden - access denied")

        if status_code >= 500:
            return StopCondition(True, f"Server error: HTTP {status_code}")

        # Check for URL revisit (circular pagination)
        if self.track_urls:
            if url in self.visited_urls:
                return StopCondition(True, f"Circular pagination detected: revisited {url}")
            self.visited_urls.add(url)

        # Check for empty content
        content_bytes = content if isinstance(content, bytes) else content.encode("utf-8")
        if len(content_bytes) < self.min_content_length:
            self.consecutive_empty += 1
            if self.consecutive_empty >= self.max_empty_responses:
                reason = (
                    f"{self.consecutive_empty} consecutive empty responses "
                    f"(< {self.min_content_length} bytes)"
                )
                return StopCondition(True, reason)
        else:
            self.consecutive_empty = 0

        # Check for duplicate content
        if self.track_content_hashes and content_bytes:
            content_hash = hashlib.sha256(content_bytes).hexdigest()
            if content_hash in self.visited_hashes:
                return StopCondition(True, "Duplicate content detected (identical page)")
            self.visited_hashes.add(content_hash)

        return StopCondition(False, "")

    def reset(self) -> None:
        """Reset detector state for new pagination sequence."""
        self.visited_hashes.clear()
        self.visited_urls.clear()
        self.consecutive_empty = 0
