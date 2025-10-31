"""HTML parsing and selector application service."""

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup
from lxml import etree  # type: ignore[import-untyped]

from crawler.core.logging import get_logger

logger = get_logger(__name__)


class HTMLParserService:
    """Service for parsing HTML and applying selectors.

    Supports both CSS selectors (via BeautifulSoup) and XPath expressions (via lxml).
    """

    def __init__(self) -> None:
        """Initialize HTML parser service."""
        pass

    def parse_html(self, content: str | bytes, parser: str = "lxml") -> BeautifulSoup:
        """Parse HTML content into BeautifulSoup object.

        Args:
            content: HTML content as string or bytes
            parser: Parser to use (default: "lxml" for speed)

        Returns:
            BeautifulSoup object

        Raises:
            ValueError: If content is empty or invalid
        """
        if not content:
            raise ValueError("HTML content cannot be empty")

        try:
            if isinstance(content, bytes):
                content = content.decode("utf-8", errors="replace")
            return BeautifulSoup(content, parser)
        except Exception as e:
            logger.error("html_parse_error", error=str(e))
            raise ValueError(f"Failed to parse HTML: {e}") from e

    def parse_html_raw(self, content: str | bytes) -> etree._Element:
        """Parse HTML content into lxml Element tree.

        This method returns the raw lxml tree, which can be reused for multiple
        XPath queries without re-parsing the HTML content each time.

        Args:
            content: HTML content as string or bytes

        Returns:
            lxml Element tree object

        Raises:
            ValueError: If content is empty or invalid

        Example:
            >>> tree = html_parser.parse_html_raw('<html>...</html>')
            >>> links = html_parser.apply_xpath(tree, "//a/@href")
            >>> titles = html_parser.apply_xpath(tree, "//h1/text()")
        """
        if not content:
            raise ValueError("HTML content cannot be empty")

        try:
            if isinstance(content, str):
                content = content.encode("utf-8")

            # Parse with lxml's HTML parser
            parser = etree.HTMLParser(encoding="utf-8")
            tree = etree.fromstring(content, parser)

            logger.debug("html_raw_parsed", tree_element=tree.tag)
            return tree
        except Exception as e:
            logger.error("html_raw_parse_error", error=str(e))
            raise ValueError(f"Failed to parse HTML with lxml: {e}") from e

    def apply_css_selector(
        self,
        soup: BeautifulSoup,
        selector: str,
        attribute: str | None = None,
        select_all: bool = False,
    ) -> list[str]:
        """Apply CSS selector to BeautifulSoup object.

        Args:
            soup: BeautifulSoup object
            selector: CSS selector string (e.g., "a.article-link", ".title")
            attribute: Attribute to extract (e.g., "href", "src"). If None, extracts text.
            select_all: If True, return all matches. If False, return first match only.

        Returns:
            List of extracted values (empty list if no matches)

        Example:
            >>> soup = BeautifulSoup('<a href="/article" class="link">Title</a>', "lxml")
            >>> apply_css_selector(soup, "a.link", "href", select_all=True)
            ['/article']
        """
        try:
            elements = soup.select(selector) if select_all else [soup.select_one(selector)]
            results = []

            for element in elements:
                if element is None:
                    continue

                if attribute:
                    # Extract attribute value
                    value = element.get(attribute)
                    if value:
                        # Handle list attributes (e.g., class="link1 link2")
                        if isinstance(value, list):
                            results.append(" ".join(value))
                        else:
                            results.append(str(value))
                else:
                    # Extract text content
                    text = element.get_text(strip=True)
                    if text:
                        results.append(text)

            logger.debug(
                "css_selector_applied",
                selector=selector,
                attribute=attribute,
                matches=len(results),
            )
            return results

        except Exception as e:
            logger.error(
                "css_selector_error",
                selector=selector,
                attribute=attribute,
                error=str(e),
            )
            return []

    def select_elements(
        self,
        soup: BeautifulSoup,
        selector: str,
        select_all: bool = False,
    ) -> list[Any]:
        """Select HTML elements using CSS selector.

        This method returns the actual BeautifulSoup Tag objects, not extracted values.

        Args:
            soup: BeautifulSoup object
            selector: CSS selector string (e.g., "a.article-link", ".title")
            select_all: If True, return all matches. If False, return first match only.

        Returns:
            List of BeautifulSoup Tag objects (empty list if no matches)

        Example:
            >>> soup = BeautifulSoup('<div><a href="/article">Link</a></div>', "lxml")
            >>> select_elements(soup, "a", select_all=True)
            [<a href="/article">Link</a>]
        """
        try:
            if select_all:
                elements = soup.select(selector)
            else:
                element = soup.select_one(selector)
                elements = [element] if element else []

            # Filter out None values
            return [el for el in elements if el is not None]

        except Exception as e:
            logger.error(
                "select_elements_error",
                selector=selector,
                error=str(e),
            )
            return []

    def apply_xpath(
        self,
        content: str | bytes | etree._Element,
        xpath: str,
        attribute: str | None = None,
    ) -> list[str]:
        """Apply XPath expression to HTML content or parsed tree.

        Args:
            content: HTML content as string/bytes, OR pre-parsed lxml tree element
            xpath: XPath expression (e.g., "//a[@class='article-link']")
            attribute: Attribute to extract (e.g., "href"). If None, extracts text.

        Returns:
            List of extracted values (empty list if no matches)

        Example:
            >>> apply_xpath('<a href="/article">Title</a>', "//a", "href")
            ['/article']

            # Using pre-parsed tree for multiple queries
            >>> tree = html_parser.parse_html_raw('<html>...</html>')
            >>> results1 = apply_xpath(tree, "//a/@href")
            >>> results2 = apply_xpath(tree, "//h1/text()")
        """
        try:
            # If content is raw HTML string/bytes, parse it
            if isinstance(content, (str, bytes)):
                if isinstance(content, str):
                    content = content.encode("utf-8")
                # Parse with lxml's HTML parser
                parser = etree.HTMLParser(encoding="utf-8")
                tree = etree.fromstring(content, parser)
            else:
                # Content is already a parsed lxml tree
                tree = content

            # Apply XPath
            elements = tree.xpath(xpath)
            results = []

            for element in elements:
                if isinstance(element, str):
                    # XPath returned text directly (e.g., //a/text())
                    results.append(element.strip())
                elif hasattr(element, "text"):
                    # XPath returned element
                    if attribute:
                        value = element.get(attribute)
                        if value:
                            results.append(str(value))
                    else:
                        # Extract all text content including from child elements
                        text_content = "".join(element.itertext())
                        if text_content:
                            results.append(text_content.strip())

            logger.debug(
                "xpath_applied",
                xpath=xpath,
                attribute=attribute,
                matches=len(results),
            )
            return results

        except Exception as e:
            logger.error(
                "xpath_error",
                xpath=xpath,
                attribute=attribute,
                error=str(e),
            )
            return []

    def extract_data(
        self,
        content: str | bytes,
        selector: str,
        attribute: str | None = None,
        selector_type: str = "css",
        result_type: str = "single",
    ) -> str | list[str] | None:
        """Extract data from HTML using selector.

        This is a high-level method that automatically determines whether to use
        CSS or XPath, and returns single value or list based on result_type.

        Args:
            content: HTML content as string or bytes
            selector: CSS selector or XPath expression
            attribute: Attribute to extract (e.g., "href", "src"). If None, extracts text.
            selector_type: "css" or "xpath" (default: "css")
            result_type: "single" or "array" (default: "single")

        Returns:
            - If result_type="single": First match as string, or None if no match
            - If result_type="array": List of all matches (empty list if no matches)

        Example:
            >>> extract_data('<a href="/article">Title</a>', "a", "href", result_type="single")
            '/article'
        """
        if selector_type == "xpath":
            results = self.apply_xpath(content, selector, attribute)
        else:
            soup = self.parse_html(content)
            select_all = result_type == "array"
            results = self.apply_css_selector(soup, selector, attribute, select_all=select_all)

        # Return based on result_type
        if result_type == "single":
            return results[0] if results else None
        return results

    def extract_data_from_parsed(
        self,
        parsed_content: BeautifulSoup | etree._Element,
        selector: str,
        attribute: str | None = None,
        selector_type: str = "css",
        result_type: str = "single",
    ) -> str | list[str] | None:
        """Extract data from pre-parsed HTML using selector.

        This is an optimized version that accepts pre-parsed HTML objects to avoid
        re-parsing the same content when performing multiple extractions.

        Args:
            parsed_content: Pre-parsed BeautifulSoup object or lxml Element tree
            selector: CSS selector or XPath expression
            attribute: Attribute to extract (e.g., "href", "src"). If None, extracts text.
            selector_type: "css" or "xpath" (default: "css")
            result_type: "single" or "array" (default: "single")

        Returns:
            - If result_type="single": First match as string, or None if no match
            - If result_type="array": List of all matches (empty list if no matches)

        Example:
            >>> soup = html_parser.parse_html(html_content)
            >>> links = html_parser.extract_data_from_parsed(
            ...     soup, "a.link", "href", result_type="array"
            ... )
            >>>
            >>> tree = html_parser.parse_html_raw(html_content)
            >>> titles = html_parser.extract_data_from_parsed(
            ...     tree, "//h1/text()", selector_type="xpath"
            ... )
        """
        if selector_type == "xpath":
            results = self.apply_xpath(parsed_content, selector, attribute)
        else:
            select_all = result_type == "array"
            results = self.apply_css_selector(
                parsed_content, selector, attribute, select_all=select_all
            )

        # Return based on result_type
        if result_type == "single":
            return results[0] if results else None
        return results

    def resolve_relative_url(self, url: str, base_url: str) -> str:
        """Resolve relative URL against base URL.

        Args:
            url: URL to resolve (can be relative or absolute)
            base_url: Base URL to resolve against

        Returns:
            Absolute URL

        Example:
            >>> resolve_relative_url("/article", "https://example.com/page")
            'https://example.com/article'
            >>> resolve_relative_url("https://other.com/article", "https://example.com")
            'https://other.com/article'
        """
        if not url or not base_url:
            raise ValueError(f"Failed to resolve URL '{url}' with base '{base_url}'")

        try:
            # urljoin handles both relative and absolute URLs correctly
            absolute_url = urljoin(base_url, url)
            logger.debug("url_resolved", relative=url, base=base_url, absolute=absolute_url)
            return absolute_url
        except Exception as e:
            logger.error("url_resolve_error", url=url, base_url=base_url, error=str(e))
            raise ValueError(f"Failed to resolve URL '{url}' with base '{base_url}'") from e

    def extract_url_metadata(
        self,
        soup: BeautifulSoup,
        link_element: Any,
        metadata_fields: dict[str, str] | None = None,
        parent_selector: str | None = None,
    ) -> dict[str, Any]:
        """Extract metadata associated with a URL link element.

        Args:
            soup: BeautifulSoup object of the page
            link_element: BeautifulSoup element (e.g., <a> tag)
            metadata_fields: Dict of field_name -> CSS_selector for metadata extraction
            parent_selector: CSS selector to find the parent container that contains
                           both the link and its metadata (e.g., "article", ".item")

        Returns:
            Dictionary of metadata (title, preview, etc.)

        Example:
            >>> soup = BeautifulSoup(
            ...     '<article><h3>Title</h3><a href="/article">Link</a></article>', "lxml"
            ... )
            >>> link = soup.select_one("a")
            >>> extract_url_metadata(soup, link, {"title": "h3"}, parent_selector="article")
            {'title': 'Title', 'preview': None}
        """
        metadata: dict[str, Any] = {"title": None, "preview": None}

        try:
            # Try to get title from link text first
            if link_element:
                title_text = link_element.get_text(strip=True)
                if title_text:
                    metadata["title"] = title_text

            # Determine the search scope for metadata
            search_scope = soup
            if link_element:
                if parent_selector:
                    # Walk up the DOM tree to find the nearest parent matching parent_selector
                    current = link_element
                    while current and current.parent:
                        # Simple selector matching for common cases
                        if parent_selector.startswith('.'):
                            # Class selector
                            class_name = parent_selector[1:]
                            if current.has_attr('class') and class_name in current['class']:
                                search_scope = current
                                break
                        elif parent_selector.startswith('#'):
                            # ID selector
                            if current.get('id') == parent_selector[1:]:
                                search_scope = current
                                break
                        else:
                            # Tag selector
                            if current.name == parent_selector:
                                search_scope = current
                                break
                        current = current.parent
                else:
                    # If no parent selector provided, use the link's immediate parent
                    search_scope = link_element.parent or soup

            # Apply custom metadata selectors if provided
            if metadata_fields:
                for field_name, selector in metadata_fields.items():
                    if selector:
                        value = self.apply_css_selector(
                            search_scope, selector, attribute=None, select_all=False
                        )
                        if value:
                            metadata[field_name] = value[0]

        except Exception as e:
            logger.error("metadata_extraction_error", error=str(e))

        return metadata
