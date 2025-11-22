"""HTTP step executor for standard HTTP requests.

Handles HTTP/HTTPS requests without browser automation.
"""

from __future__ import annotations

from typing import Any

import httpx

from crawler.core.logging import get_logger
from crawler.services.executor_retry import execute_with_retry
from crawler.services.local_rate_limiter import LocalRateLimiter
from crawler.services.selector_processor import SelectorProcessor
from crawler.services.step_executors.base import BaseStepExecutor, ExecutionResult

logger = get_logger(__name__)


class HTTPExecutor(BaseStepExecutor):
    """Executor for HTTP method steps using httpx client."""

    def __init__(
        self,
        selector_processor: SelectorProcessor | None = None,
        client: httpx.AsyncClient | None = None,
        rate_limiter: LocalRateLimiter | None = None,
    ):
        """Initialize HTTP executor.

        Args:
            selector_processor: Selector processor for data extraction
            client: httpx AsyncClient instance (creates new one if None)
            rate_limiter: Rate limiter for request throttling (optional)
        """
        self.selector_processor = selector_processor or SelectorProcessor()
        self._client = client
        self._owns_client = client is None
        self.rate_limiter = rate_limiter

    async def execute(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute HTTP request and extract data with retry logic.

        Args:
            url: Target URL
            step_config: Configuration (timeout, headers, retry, etc.)
            selectors: Selectors for data extraction

        Returns:
            ExecutionResult with response content and extracted data
        """
        # Extract retry config and wrap execution with retry logic
        retry_config = step_config.get("retry", {})

        return await execute_with_retry(
            func=lambda: self._execute_once(url, step_config, selectors),
            retry_config=retry_config,
            operation_name="http_request",
            url=url,
        )

    async def _execute_once(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute HTTP request once (no retry logic - called by execute_with_retry).

        Args:
            url: Target URL
            step_config: Configuration (timeout, headers, etc.)
            selectors: Selectors for data extraction

        Returns:
            ExecutionResult with response content and extracted data
        """
        # Extract timeout from merged config (handles GlobalConfig.timeout.http_request)
        # Initialize before try block to avoid UnboundLocalError in exception handlers
        timeout_config = step_config.get("timeout", {})
        if isinstance(timeout_config, dict):
            # GlobalConfig structure: {"http_request": 30, "page_load": 30, "selector_wait": 10}
            timeout = timeout_config.get("http_request", 30)
        else:
            # Legacy: timeout as integer
            timeout = timeout_config if isinstance(timeout_config, (int, float)) else 30

        try:
            # Get or create client
            client = await self._get_client()

            headers = step_config.get("headers", {})
            method = step_config.get("http_method", "GET").upper()

            # Make HTTP request (with rate limiting if configured)
            logger.info(
                "http_request_starting",
                url=url,
                method=method,
                timeout=timeout,
                rate_limited=self.rate_limiter is not None,
            )

            # Apply rate limiting if configured
            if self.rate_limiter:
                async with self.rate_limiter.acquire():
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        timeout=timeout,
                        follow_redirects=True,
                    )
            else:
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
                # Log error - classification handled by executor_retry.py
                logger.warning(
                    "http_request_failed",
                    url=url,
                    status_code=response.status_code,
                    status_name=status_name,
                )

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
            # Timeouts are retryable - classification handled by executor_retry.py
            logger.warning(
                "http_request_timeout",
                url=url,
                timeout=timeout,
                exception="TimeoutException",
            )
            return self._create_error_result(
                f"Request timeout: {e}",
                url=url,
                timeout=timeout,
            )
        except httpx.RequestError as e:
            # Network errors are typically retryable - classification handled by executor_retry.py
            logger.warning(
                "http_request_error",
                url=url,
                exception="RequestError",
                error_message=str(e),
            )
            return self._create_error_result(
                f"Request error: {e}",
                url=url,
            )
        except Exception as e:
            # Unknown exceptions - classification handled by executor_retry.py
            logger.error(
                "http_unexpected_error",
                url=url,
                exception=type(e).__name__,
                error_message=str(e),
                exc_info=True,
            )
            return self._create_error_result(
                f"Unexpected error: {e}",
                url=url,
            )

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create httpx client.

        Note: Timeout is passed per-request to allow GlobalConfig.timeout.http_request
        to be applied dynamically. No default timeout is set on the client.

        Returns:
            httpx.AsyncClient instance
        """
        if self._client is None:
            self._client = httpx.AsyncClient(
                follow_redirects=True,
                timeout=None,  # Timeout passed per-request for flexibility
            )
        return self._client

    async def cleanup(self) -> None:
        """Clean up HTTP client resources."""
        if self._client is not None and self._owns_client:
            await self._client.aclose()
            self._client = None  # Clear reference to allow new client creation
            logger.debug("http_client_closed")
