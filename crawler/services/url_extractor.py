"""URL extraction service for detail pages from list pages."""

from dataclasses import dataclass
from typing import Any

from crawler.api.generated import SelectorConfig
from crawler.api.generated.models import Type2
from crawler.core.logging import get_logger
from crawler.services.html_parser import HTMLParserService
from crawler.services.redis_cache import URLDeduplicationCache
from crawler.utils.url import hash_url, normalize_url

logger = get_logger(__name__)


@dataclass
class ExtractedURL:
    """Represents an extracted URL with metadata."""

    url: str
    normalized_url: str
    url_hash: str
    title: str | None = None
    preview: str | None = None
    metadata: dict[str, Any] | None = None


class URLExtractorService:
    """Service for extracting detail page URLs from listing pages.

    Features:
    - Apply CSS/XPath selectors to extract URLs
    - Extract metadata (title, preview) for each URL
    - Handle relative URLs correctly
    - Handle URLs in data attributes
    - Deduplicate URLs within crawl session
    """

    def __init__(
        self,
        html_parser: HTMLParserService,
        dedup_cache: URLDeduplicationCache | None = None,
    ) -> None:
        """Initialize URL extractor service.

        Args:
            html_parser: HTML parser service for selector application
            dedup_cache: Optional URL deduplication cache (for crawl-level dedup)
        """
        self.html_parser = html_parser
        self.dedup_cache = dedup_cache

    async def extract_urls(
        self,
        html_content: str | bytes,
        base_url: str,
        url_selector: str | SelectorConfig,
        metadata_selectors: dict[str, str] | None = None,
        deduplicate: bool = True,
        job_id: str | None = None,
    ) -> list[ExtractedURL]:
        """Extract detail page URLs from list page HTML.

        Args:
            html_content: HTML content of the list page
            base_url: Base URL for resolving relative URLs
            url_selector: Selector for extracting URLs (string or SelectorConfig)
            metadata_selectors: Optional dict of field_name -> CSS_selector for metadata
            deduplicate: If True, deduplicate URLs within this extraction
            job_id: Optional job ID for deduplication cache tracking

        Returns:
            List of ExtractedURL objects with normalized URLs and metadata

        Example:
            ```python
            # Simple CSS selector (string)
            urls = await extractor.extract_urls(
                html_content='<a href="/article" class="link">Article Title</a>',
                base_url="https://example.com",
                url_selector="a.link",
            )

            # Full SelectorConfig with href attribute
            config = SelectorConfig(
                selector="a.article-link",
                attribute="href",
                type="array"
            )
            urls = await extractor.extract_urls(
                html_content=html,
                base_url="https://example.com",
                url_selector=config,
                metadata_selectors={"title": "h3.article-title"},
            )
            ```
        """
        logger.info(
            "extracting_urls",
            base_url=base_url,
            selector=url_selector,
            deduplicate=deduplicate,
        )

        # Parse selector configuration
        selector, attribute, result_type, selector_type = self._parse_selector_config(url_selector)

        # Extract URLs using selector
        raw_urls = self.html_parser.extract_data(
            content=html_content,
            selector=selector,
            attribute=attribute,
            selector_type=selector_type,
            result_type=result_type,
        )

        # Normalize to list
        if isinstance(raw_urls, str):
            raw_urls = [raw_urls]
        elif raw_urls is None:
            raw_urls = []

        logger.debug("urls_extracted_raw", count=len(raw_urls))

        # Process each URL
        extracted_urls: list[ExtractedURL] = []
        seen_hashes: set[str] = set()  # For within-extraction deduplication

        for raw_url in raw_urls:
            if not raw_url or not isinstance(raw_url, str):
                continue

            # Resolve relative URLs
            absolute_url = self.html_parser.resolve_relative_url(raw_url, base_url)

            # Normalize and hash
            try:
                normalized = normalize_url(absolute_url)
                url_hash = hash_url(absolute_url, normalize=True)
            except ValueError as e:
                logger.warning("url_normalization_failed", url=absolute_url, error=str(e))
                continue

            # Skip if duplicate within this extraction
            if deduplicate and url_hash in seen_hashes:
                logger.debug("url_duplicate_within_extraction", url=normalized)
                continue

            # Check deduplication cache if available
            if deduplicate and self.dedup_cache:
                if await self.dedup_cache.exists(url_hash):
                    logger.debug("url_duplicate_in_cache", url=normalized)
                    continue

            # Extract metadata (if selectors provided)
            metadata: dict[str, Any] = {}
            if metadata_selectors:
                for field_name, meta_selector in metadata_selectors.items():
                    value = self.html_parser.extract_data(
                        content=html_content,
                        selector=meta_selector,
                        attribute=None,
                        result_type="single",
                    )
                    if value:
                        metadata[field_name] = value

            # Create extracted URL object
            extracted = ExtractedURL(
                url=absolute_url,
                normalized_url=normalized,
                url_hash=url_hash,
                title=metadata.get("title"),
                preview=metadata.get("preview"),
                metadata=metadata if metadata else None,
            )
            extracted_urls.append(extracted)

            # Track for within-extraction deduplication
            if deduplicate:
                seen_hashes.add(url_hash)

            # Store in deduplication cache if available
            if deduplicate and self.dedup_cache and job_id:
                await self.dedup_cache.set(
                    url_hash,
                    {
                        "url": normalized,
                        "job_id": job_id,
                        "extracted_from": base_url,
                    },
                )

        logger.info(
            "urls_extracted",
            base_url=base_url,
            raw_count=len(raw_urls),
            unique_count=len(extracted_urls),
        )

        return extracted_urls

    def _parse_selector_config(
        self, selector_config: str | SelectorConfig
    ) -> tuple[str, str | None, str, str]:
        """Parse selector configuration into components.

        Args:
            selector_config: String selector or SelectorConfig object

        Returns:
            Tuple of (selector, attribute, result_type, selector_type)

        Example:
            >>> _parse_selector_config("a.link")
            ('a.link', 'href', 'array', 'css')

            >>> _parse_selector_config(SelectorConfig(selector="//a", attribute="href"))
            ('//a', 'href', 'single', 'xpath')
        """
        # Default values
        selector: str
        attribute: str | None = "href"  # Default to href for URL extraction
        result_type: str = "array"  # Default to array for multiple URLs
        selector_type: str = "css"  # Default to CSS

        if isinstance(selector_config, str):
            # Simple string selector
            selector = selector_config
        else:
            # Full SelectorConfig object
            selector = selector_config.selector
            attribute = selector_config.attribute or "href"
            # Convert enum to string value
            if selector_config.type:
                result_type = selector_config.type.value
            else:
                result_type = "array"

            # Detect XPath if selector starts with // or /
            if selector.startswith(("//", "/")):
                selector_type = "xpath"

        return selector, attribute, result_type, selector_type

    async def extract_urls_from_data_attributes(
        self,
        html_content: str | bytes,
        base_url: str,
        element_selector: str,
        data_attribute: str,
        deduplicate: bool = True,
        job_id: str | None = None,
    ) -> list[ExtractedURL]:
        """Extract URLs from data attributes (e.g., data-url, data-href).

        Many modern websites store URLs in data attributes instead of href.

        Args:
            html_content: HTML content of the page
            base_url: Base URL for resolving relative URLs
            element_selector: CSS selector for elements containing data attributes
            data_attribute: Name of data attribute (e.g., "data-url", "data-href")
            deduplicate: If True, deduplicate URLs
            job_id: Optional job ID for cache tracking

        Returns:
            List of ExtractedURL objects

        Example:
            ```python
            # Extract from <div class="article" data-url="/article/123">
            urls = await extractor.extract_urls_from_data_attributes(
                html_content=html,
                base_url="https://example.com",
                element_selector="div.article",
                data_attribute="data-url",
            )
            ```
        """
        logger.info(
            "extracting_urls_from_data_attributes",
            base_url=base_url,
            element_selector=element_selector,
            data_attribute=data_attribute,
        )

        # Create selector config with the data attribute
        config = SelectorConfig(
            selector=element_selector, attribute=data_attribute, type=Type2.array
        )

        # Use the main extract_urls method
        return await self.extract_urls(
            html_content=html_content,
            base_url=base_url,
            url_selector=config,
            deduplicate=deduplicate,
            job_id=job_id,
        )
