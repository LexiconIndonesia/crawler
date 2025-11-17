"""HTTP step executor for standard HTTP requests.

Handles HTTP/HTTPS requests without browser automation.
"""

from __future__ import annotations

from typing import Any

import httpx

from crawler.core.logging import get_logger
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors.base import BaseStepExecutor, ExecutionResult

logger = get_logger(__name__)


class HTTPExecutor(BaseStepExecutor):
    """Executor for HTTP method steps using httpx client."""

    def __init__(
        self,
        selector_processor: SelectorProcessor | None = None,
        client: httpx.AsyncClient | None = None,
    ):
        """Initialize HTTP executor.

        Args:
            selector_processor: Selector processor for data extraction
            client: httpx AsyncClient instance (creates new one if None)
        """
        self.selector_processor = selector_processor or SelectorProcessor()
        self._client = client
        self._owns_client = client is None

    async def execute(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute HTTP request and extract data.

        Args:
            url: Target URL
            step_config: Configuration (timeout, headers, etc.)
            selectors: Selectors for data extraction

        Returns:
            ExecutionResult with response content and extracted data
        """
        try:
            # Get or create client
            client = await self._get_client()

            # Extract config
            timeout = step_config.get("timeout", 30)
            headers = step_config.get("headers", {})
            method = step_config.get("http_method", "GET").upper()

            # Make HTTP request
            logger.info(
                "http_request_starting",
                url=url,
                method=method,
                timeout=timeout,
            )

            response = await client.request(
                method=method,
                url=url,
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            )

            # Get descriptive status message (e.g., "200 OK", "404 Not Found")
            status_name = response.reason_phrase or "Unknown"

            # Check status
            if not 200 <= response.status_code < 300:
                return self._create_error_result(
                    f"HTTP {response.status_code} {status_name}",
                    url=url,
                    status_code=response.status_code,
                    status_name=status_name,
                )

            # Get content
            content = response.text

            # Extract data using selectors
            extracted_data = {}
            if selectors:
                extracted_data = self.selector_processor.process_selectors(content, selectors)

            logger.info(
                "http_request_completed",
                url=url,
                status_code=response.status_code,
                status_name=status_name,
                content_length=len(content),
                extracted_fields=len(extracted_data),
            )

            return self._create_success_result(
                content=content,
                extracted_data=extracted_data,
                status_code=response.status_code,
                status_name=status_name,
                content_length=len(content),
                headers=dict(response.headers),
            )

        except httpx.TimeoutException as e:
            return self._create_error_result(
                f"Request timeout: {e}",
                url=url,
                timeout=timeout,
            )
        except httpx.RequestError as e:
            return self._create_error_result(
                f"Request error: {e}",
                url=url,
            )
        except Exception as e:
            return self._create_error_result(
                f"Unexpected error: {e}",
                url=url,
            )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx client.

        Returns:
            httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=30.0,
            )
        return self._client

    async def cleanup(self) -> None:
        """Clean up HTTP client resources."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None  # Clear reference to allow new client creation
            logger.debug("http_client_closed")
