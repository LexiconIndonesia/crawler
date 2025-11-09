"""Selector processor for extracting data from HTML and JSON responses.

This module provides unified data extraction from various content types using
selectors (CSS, XPath) for HTML and JSON path for API responses.
"""

from __future__ import annotations

from typing import Any

from crawler.core.logging import get_logger
from crawler.services.html_parser import HTMLParserService

logger = get_logger(__name__)


class SelectorProcessor:
    """Processes selectors to extract data from HTML and JSON content.

    Supports:
    - CSS selectors for HTML
    - XPath expressions for HTML
    - JSON path queries for API responses
    """

    def __init__(self, html_parser: HTMLParserService | None = None):
        """Initialize selector processor.

        Args:
            html_parser: HTML parser service instance. If None, creates a new one.
        """
        self.html_parser = html_parser or HTMLParserService()

    def process_selectors(
        self,
        content: str | dict[str, Any],
        selectors: dict[str, Any],
    ) -> dict[str, Any]:
        """Process all selectors against content and return extracted data.

        Args:
            content: HTML string or JSON dict to extract data from
            selectors: Dictionary of field_name -> selector configuration

        Returns:
            Dictionary of field_name -> extracted value(s)

        Example:
            >>> content = '<div><h1>Title</h1><a href="/link">Link</a></div>'
            >>> selectors = {
            ...     "title": "h1",
            ...     "link": {"selector": "a", "attribute": "href"}
            ... }
            >>> processor.process_selectors(content, selectors)
            {'title': 'Title', 'link': '/link'}
        """
        if not selectors:
            return {}

        # Determine content type
        is_json = isinstance(content, dict)
        extracted_data = {}

        for field_name, selector_config in selectors.items():
            try:
                if is_json:
                    # Type narrowing: content is dict at this point
                    assert isinstance(content, dict)
                    value = self._extract_from_json(content, selector_config)
                else:
                    # Type narrowing: content is str at this point
                    assert isinstance(content, str)
                    value = self._extract_from_html(content, selector_config)

                extracted_data[field_name] = value
                logger.debug(
                    "selector_processed",
                    field=field_name,
                    content_type="json" if is_json else "html",
                    has_value=value is not None,
                )
            except Exception as e:
                logger.error(
                    "selector_processing_error",
                    field=field_name,
                    selector=selector_config,
                    error=str(e),
                )
                extracted_data[field_name] = None

        return extracted_data

    def _extract_from_html(
        self,
        content: str,
        selector_config: str | dict[str, Any],
    ) -> str | list[str] | None:
        """Extract data from HTML content using selector.

        Args:
            content: HTML content string
            selector_config: Selector configuration (string or dict)

        Returns:
            Extracted value(s) or None

        Raises:
            ValueError: If selector is invalid
        """
        # Parse selector config
        if isinstance(selector_config, str):
            # Simple string selector - defaults to CSS, single result, text
            selector = selector_config
            attribute = None
            result_type = "single"
        elif isinstance(selector_config, dict):
            selector_value = selector_config.get("selector")
            if not selector_value or not isinstance(selector_value, str):
                raise ValueError("Selector configuration must include 'selector' field")
            selector = selector_value
            attribute = selector_config.get("attribute")
            result_type = selector_config.get("type", "single")
        else:
            raise ValueError(f"Invalid selector configuration: {type(selector_config).__name__}")

        # Auto-detect selector type (XPath vs CSS)
        selector_type = self._detect_selector_type(selector)

        # Extract data using HTML parser
        return self.html_parser.extract_data(
            content=content,
            selector=selector,
            attribute=attribute,
            selector_type=selector_type,
            result_type=result_type,
        )

    def _extract_from_json(
        self,
        content: dict[str, Any],
        selector_config: str | dict[str, Any],
    ) -> Any:
        """Extract data from JSON content using JSON path.

        Args:
            content: JSON dictionary
            selector_config: Selector configuration (string or dict)

        Returns:
            Extracted value(s) or None

        Note:
            JSON path syntax: "field.nested.array[0].value"
            Use simple dot notation for now (can be enhanced with JSONPath library)
        """
        # Parse selector config
        if isinstance(selector_config, str):
            path = selector_config
            result_type = "single"
        elif isinstance(selector_config, dict):
            path_value = selector_config.get("selector")
            if not path_value or not isinstance(path_value, str):
                raise ValueError("Selector configuration must include 'selector' field")
            path = path_value
            result_type = selector_config.get("type", "single")
        else:
            raise ValueError(f"Invalid selector configuration: {type(selector_config).__name__}")

        # Navigate JSON path
        value = self._navigate_json_path(content, path)

        # Handle array result type
        if result_type == "array" and not isinstance(value, list):
            return [value] if value is not None else []

        return value

    def _navigate_json_path(self, data: dict[str, Any], path: str) -> Any:
        """Navigate a JSON path to extract value.

        Args:
            data: JSON dictionary
            path: Dot-separated path (e.g., "data.items.0.title")

        Returns:
            Value at path or None if not found

        Example:
            >>> data = {"data": {"items": [{"title": "Hello"}]}}
            >>> _navigate_json_path(data, "data.items.0.title")
            'Hello'
        """
        if not path:
            return data

        parts = path.split(".")
        current: Any = data

        for part in parts:
            if current is None:
                return None

            # Handle array indexing
            if isinstance(current, list):
                try:
                    index = int(part)
                    current = current[index] if 0 <= index < len(current) else None
                except (ValueError, TypeError):
                    logger.error(
                        "json_path_array_index_error",
                        part=part,
                        path=path,
                    )
                    return None
            elif isinstance(current, dict):
                current = current.get(part)
            else:
                logger.debug(
                    "json_path_navigation_stopped",
                    part=part,
                    path=path,
                    current_type=type(current).__name__,
                )
                return None

        return current

    def _detect_selector_type(self, selector: str) -> str:
        """Detect if selector is XPath or CSS.

        Args:
            selector: Selector string

        Returns:
            "xpath" or "css"

        Note:
            XPath expressions typically start with / or //
            Everything else is treated as CSS selector
        """
        if selector.startswith("/") or selector.startswith("//"):
            return "xpath"
        return "css"

    def extract_single_field(
        self,
        content: str | dict[str, Any],
        selector: str,
        attribute: str | None = None,
    ) -> Any:
        """Extract a single field value from content.

        Helper method for quick single-field extraction.

        Args:
            content: HTML string or JSON dict
            selector: Selector string
            attribute: Attribute to extract (HTML only)

        Returns:
            Extracted value or None
        """
        selector_config = {"selector": selector, "type": "single"}
        if attribute:
            selector_config["attribute"] = attribute

        if isinstance(content, str):
            return self._extract_from_html(content, selector_config)
        else:
            return self._extract_from_json(content, selector_config)

    def extract_multiple_fields(
        self,
        content: str | dict[str, Any],
        selector: str,
        attribute: str | None = None,
    ) -> list[str]:
        """Extract multiple field values from content.

        Helper method for quick multi-field extraction.

        Args:
            content: HTML string or JSON dict
            selector: Selector string
            attribute: Attribute to extract (HTML only)

        Returns:
            List of extracted values (empty list if none found)
        """
        selector_config = {"selector": selector, "type": "array"}
        if attribute:
            selector_config["attribute"] = attribute

        result = (
            self._extract_from_html(content, selector_config)
            if isinstance(content, str)
            else self._extract_from_json(content, selector_config)
        )

        # Ensure list return type
        if result is None:
            return []
        if isinstance(result, list):
            return result
        return [result]
