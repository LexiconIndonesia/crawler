"""Content normalization service for removing dynamic elements before hashing.

This service extracts and normalizes main content from HTML pages, removing
dynamic elements like timestamps, ads, navigation, and other boilerplate that
would cause false hash mismatches for otherwise identical content.

The normalized content can then be hashed (e.g., with Simhash) for reliable
duplicate detection and content similarity comparison.
"""

import re

from bs4 import BeautifulSoup, Comment
from bs4.element import Tag

from crawler.core.logging import get_logger

logger = get_logger(__name__)


class ContentNormalizer:
    """Service for normalizing HTML content before hashing.

    Removes dynamic elements, boilerplate, and noise to extract stable
    main content suitable for duplicate detection and similarity matching.

    Example:
        >>> normalizer = ContentNormalizer()
        >>> html = '<html><body><article>Main content</article></body></html>'
        >>> normalized = normalizer.normalize(html)
        >>> print(normalized)
        'main content'
    """

    # HTML elements that typically contain boilerplate/navigation
    BOILERPLATE_TAGS = {
        "nav",
        "header",
        "footer",
        "aside",
        "sidebar",
        "menu",
        "noscript",
        "iframe",
        "script",
        "style",
        "link",
        "meta",
    }

    # CSS classes/IDs commonly used for ads and tracking
    AD_PATTERNS = [
        r"ad[_-]",
        r"ads[_-]",
        r"advert",
        r"sponsor",
        r"promo",
        r"banner",
        r"cookie[_-]",
        r"gdpr",
        r"consent",
        r"popup",
        r"modal",
        r"overlay",
        r"tracking",
        r"analytics",
        r"social[_-]share",
        r"share[_-]buttons?",
        r"related[_-]",
        r"recommend",
        r"newsletter",
        r"subscription",
    ]

    # Regex patterns for dynamic content
    TIMESTAMP_PATTERNS = [
        # Date with time: 2024-01-15 14:30:00, 2024-01-15T14:30:00Z (must come before simple date)
        r"\d{4}[-/]\d{2}[-/]\d{2}[T\s]\d{2}:\d{2}(:\d{2})?([+-]\d{2}:?\d{2}|Z)?",
        # ISO dates: 2024-01-15, 2024/01/15
        r"\d{4}[-/]\d{2}[-/]\d{2}",
        # Standalone times: 14:30:00, 14:30
        r"\b\d{1,2}:\d{2}(:\d{2})?\b",
        # Human readable: January 15, 2024 | Jan 15, 2024
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|"
        r"Dec(?:ember)?)\s+\d{1,2},?\s+\d{4}",
        # Relative times: 2 hours ago, 3 days ago, Updated yesterday
        r"\d+\s+(?:second|minute|hour|day|week|month|year)s?\s+ago",
        r"(?:updated|posted|published)?\s*(?:yesterday|today|just now)",
        # View counts, likes, shares: 1.2K views, 500 likes
        r"\d+[\d,.]*[KMB]?\s+(?:views?|likes?|shares?|comments?|reads?)",
        # Time ago with "Last updated": Last updated: 2 hours ago
        r"(?:last\s+)?(?:updated|modified|posted|published)[\s:]+.*?ago",
    ]

    # Compiled regex patterns (done at class level for performance)
    _compiled_ad_patterns: list[re.Pattern[str]] = []
    _compiled_timestamp_patterns: list[re.Pattern[str]] = []

    def __init__(self) -> None:
        """Initialize content normalizer with compiled regex patterns."""
        # Compile patterns once at initialization
        if not ContentNormalizer._compiled_ad_patterns:
            ContentNormalizer._compiled_ad_patterns = [
                re.compile(pattern, re.IGNORECASE) for pattern in self.AD_PATTERNS
            ]

        if not ContentNormalizer._compiled_timestamp_patterns:
            ContentNormalizer._compiled_timestamp_patterns = [
                re.compile(pattern, re.IGNORECASE) for pattern in self.TIMESTAMP_PATTERNS
            ]

        logger.debug(
            "content_normalizer_initialized",
            ad_patterns=len(self._compiled_ad_patterns),
            timestamp_patterns=len(self._compiled_timestamp_patterns),
        )

    def normalize(
        self,
        html: str | bytes,
        extract_main_only: bool = True,
        remove_timestamps: bool = True,
        preserve_structure: bool = False,
    ) -> str:
        """Normalize HTML content for hashing.

        Args:
            html: Raw HTML content as string or bytes
            extract_main_only: If True, extract only main content (remove nav, footer, etc.)
            remove_timestamps: If True, remove timestamps and dynamic date references
            preserve_structure: If True, keep paragraph breaks. If False, join into single text.

        Returns:
            Normalized text content suitable for hashing

        Raises:
            ValueError: If HTML is empty or invalid

        Example:
            >>> html = '<html><body><nav>Menu</nav><article>Content</article></body></html>'
            >>> normalizer.normalize(html)
            'content'
        """
        # Guard: Empty HTML
        if not html:
            raise ValueError("HTML content cannot be empty")

        try:
            # Parse HTML
            soup = self._parse_html(html)

            # Remove unwanted elements
            self._remove_boilerplate(soup)
            self._remove_ads_and_tracking(soup)
            self._remove_comments(soup)

            # Extract main content if requested
            content: BeautifulSoup | Tag | None = soup
            if extract_main_only:
                content = self._extract_main_content(soup)

            # Get text content
            text = self._extract_text(content, preserve_structure)

            # Remove dynamic elements from text
            if remove_timestamps:
                text = self._remove_timestamps(text)

            # Final text normalization
            text = self._normalize_text(text, preserve_structure)

            logger.debug(
                "content_normalized",
                original_size=len(html),
                normalized_size=len(text),
            )

            return text

        except Exception as e:
            logger.error("content_normalization_error", error=str(e))
            raise ValueError(f"Failed to normalize content: {e}") from e

    def _parse_html(self, html: str | bytes) -> BeautifulSoup:
        """Parse HTML into BeautifulSoup object.

        Args:
            html: HTML content as string or bytes

        Returns:
            BeautifulSoup object
        """
        if isinstance(html, bytes):
            html = html.decode("utf-8", errors="replace")

        return BeautifulSoup(html, "lxml")

    def _remove_boilerplate(self, soup: BeautifulSoup) -> None:
        """Remove boilerplate elements like navigation, headers, footers.

        Modifies soup in-place.

        Args:
            soup: BeautifulSoup object to clean
        """
        for tag_name in self.BOILERPLATE_TAGS:
            for element in soup.find_all(tag_name):
                element.decompose()

        logger.debug("boilerplate_removed", tags=list(self.BOILERPLATE_TAGS))

    def _remove_ads_and_tracking(self, soup: BeautifulSoup) -> None:
        """Remove elements with ad-related classes or IDs.

        Modifies soup in-place.

        Args:
            soup: BeautifulSoup object to clean
        """
        # Collect elements to remove (don't modify while iterating)
        elements_to_remove = []

        for element in soup.find_all(True):  # Find all tags
            # Guard: Skip if element has no attrs
            if not hasattr(element, "attrs") or element.attrs is None:
                continue

            # Check class attribute
            if element.has_attr("class"):
                classes = " ".join(element["class"])
                if self._matches_ad_pattern(classes):
                    elements_to_remove.append(element)
                    continue

            # Check id attribute
            if element.has_attr("id"):
                element_id = element.get("id", "")
                if isinstance(element_id, str) and self._matches_ad_pattern(element_id):
                    elements_to_remove.append(element)

        # Remove collected elements
        for element in elements_to_remove:
            element.decompose()

        if elements_to_remove:
            logger.debug("ads_removed", count=len(elements_to_remove))

    def _matches_ad_pattern(self, text: str) -> bool:
        """Check if text matches any ad-related pattern.

        Args:
            text: Text to check (class name or ID)

        Returns:
            True if text matches ad pattern
        """
        return any(pattern.search(text) for pattern in self._compiled_ad_patterns)

    def _remove_comments(self, soup: BeautifulSoup) -> None:
        """Remove HTML comments.

        Modifies soup in-place.

        Args:
            soup: BeautifulSoup object to clean
        """
        comments = soup.find_all(string=lambda text: isinstance(text, Comment))
        for comment in comments:
            comment.extract()

        if comments:
            logger.debug("comments_removed", count=len(comments))

    def _extract_main_content(self, soup: BeautifulSoup) -> BeautifulSoup | Tag | None:
        """Extract main content area from page.

        Looks for semantic HTML5 tags or common content containers.
        Falls back to body or full soup if no main content found.

        Args:
            soup: BeautifulSoup object

        Returns:
            BeautifulSoup object or Tag containing main content
        """
        # Try semantic HTML5 tags first
        main_candidates = ["main", "article"]
        for tag_name in main_candidates:
            element = soup.find(tag_name)
            if element:
                logger.debug("main_content_found", tag=tag_name)
                return element

        # Try common content class/ID patterns
        content_class_pattern = re.compile(r"content|main|article|post|entry", re.IGNORECASE)
        content_id_pattern = re.compile(r"content|main|article|post|entry", re.IGNORECASE)

        # Try class pattern
        element = soup.find("div", class_=content_class_pattern)
        if element:
            logger.debug("main_content_found", pattern="class")
            return element

        # Try id pattern
        element = soup.find("div", id=content_id_pattern)
        if element:
            logger.debug("main_content_found", pattern="id")
            return element

        # Fallback to body or full soup
        body = soup.find("body")
        if body:
            logger.debug("main_content_fallback", tag="body")
            return body

        logger.debug("main_content_fallback", tag="full_document")
        return soup

    def _extract_text(self, soup: BeautifulSoup | Tag | None, preserve_structure: bool) -> str:
        """Extract text content from HTML.

        Args:
            soup: BeautifulSoup object, Tag, or None
            preserve_structure: If True, keep paragraph breaks

        Returns:
            Extracted text (empty string if soup is None)
        """
        # Guard: None soup
        if soup is None:
            return ""

        if preserve_structure:
            # Keep paragraph structure
            paragraphs = []
            for element in soup.find_all(["p", "h1", "h2", "h3", "h4", "h5", "h6", "li"]):
                text = element.get_text(strip=True)
                if text:
                    paragraphs.append(text)

            return "\n".join(paragraphs) if paragraphs else ""

        # Single text block
        text = soup.get_text(separator=" ", strip=True)
        return text if text else ""

    def _remove_timestamps(self, text: str) -> str:
        """Remove timestamps and dynamic date references from text.

        Args:
            text: Text to clean

        Returns:
            Text with timestamps removed
        """
        cleaned = text
        for pattern in self._compiled_timestamp_patterns:
            cleaned = pattern.sub("", cleaned)

        return cleaned

    def _normalize_text(self, text: str, preserve_structure: bool = False) -> str:
        """Normalize whitespace and special characters.

        Args:
            text: Text to normalize
            preserve_structure: If True, preserve newlines

        Returns:
            Normalized text
        """
        if preserve_structure:
            # Normalize whitespace on each line but keep newlines
            lines = text.split("\n")
            normalized_lines = []
            for line in lines:
                # Collapse multiple spaces/tabs on each line
                line = re.sub(r"[ \t]+", " ", line)
                line = line.strip()
                if line:  # Only keep non-empty lines
                    normalized_lines.append(line.lower())
            return "\n".join(normalized_lines)

        # Normalize whitespace (multiple spaces/tabs/newlines to single space)
        text = re.sub(r"\s+", " ", text)

        # Remove leading/trailing whitespace
        text = text.strip()

        # Convert to lowercase for case-insensitive matching
        text = text.lower()

        return text

    def normalize_for_hash(self, html: str | bytes) -> str:
        """Normalize content specifically for hash generation.

        This is a convenience method that uses optimal settings for hashing:
        - Extracts main content only
        - Removes timestamps
        - Single text block (no structure)

        Args:
            html: Raw HTML content

        Returns:
            Normalized text ready for hashing

        Example:
            >>> from crawler.utils.simhash import Simhash
            >>> normalizer = ContentNormalizer()
            >>> normalized = normalizer.normalize_for_hash(html)
            >>> simhash = Simhash(normalized)
        """
        return self.normalize(
            html,
            extract_main_only=True,
            remove_timestamps=True,
            preserve_structure=False,
        )
