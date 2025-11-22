"""API step executor for JSON API requests.

Handles API requests that return JSON responses.
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


class APIExecutor(BaseStepExecutor):
    """Executor for API method steps that return JSON responses."""

    def __init__(
        self,
        selector_processor: SelectorProcessor | None = None,
        client: httpx.AsyncClient | None = None,
        rate_limiter: LocalRateLimiter | None = None,
    ):
        """Initialize API executor.

        Args:
            selector_processor: Selector processor for JSON path extraction
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
        """Execute API request and extract data from JSON response with retry logic.

        Args:
            url: Target API URL
            step_config: Configuration (timeout, headers, http_method, retry, etc.)
            selectors: JSON path selectors for data extraction

        Returns:
            ExecutionResult with JSON response and extracted data
        """
        # Extract retry config and wrap execution with retry logic
        retry_config = step_config.get("retry", {})

        return await execute_with_retry(
            func=lambda: self._execute_once(url, step_config, selectors),
            retry_config=retry_config,
            operation_name="api_request",
            url=url,
        )

    async def _execute_once(
        self,
        url: str,
        step_config: dict[str, Any],
        selectors: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        """Execute API request once (no retry logic - called by execute_with_retry).

        Args:
            url: Target API URL
            step_config: Configuration (timeout, headers, http_method, etc.)
            selectors: JSON path selectors for data extraction

        Returns:
            ExecutionResult with JSON response and extracted data
        """
        try:
            # Get or create client
            client = await self._get_client()

            # Extract timeout from merged config (handles GlobalConfig.timeout.http_request)
            timeout_config = step_config.get("timeout", {})
            if isinstance(timeout_config, dict):
                # GlobalConfig structure: {"http_request": 30, "page_load": 30, "selector_wait": 10}
                timeout = timeout_config.get("http_request", 30)
            else:
                # Legacy: timeout as integer
                timeout = timeout_config if isinstance(timeout_config, (int, float)) else 30

            headers = step_config.get("headers", {})
            method = step_config.get("http_method", "GET").upper()

            # Default to JSON content type
            if "Accept" not in headers and "accept" not in headers:
                headers["Accept"] = "application/json"

            # Make API request (with rate limiting if configured)
            logger.info(
                "api_request_starting",
                url=url,
                method=method,
                timeout=timeout,
                rate_limited=self.rate_limiter is not None,
            )

            # Extract additional request kwargs from step_config
            # This enables POST/PUT bodies, query params, files, etc.
            extra_kwargs = {
                key: step_config[key]
                for key in (
                    "params",
                    "data",
                    "json",
                    "content",
                    "files",
                    "cookies",
                    "auth",
                )
                if key in step_config
            }

            # Apply rate limiting if configured
            if self.rate_limiter:
                async with self.rate_limiter.acquire():
                    response = await client.request(
                        method=method,
                        url=url,
                        headers=headers,
                        timeout=timeout,
                        follow_redirects=True,
                        **extra_kwargs,
                    )
            else:
                response = await client.request(
                    method=method,
                    url=url,
                    headers=headers,
                    timeout=timeout,
                    follow_redirects=True,
                    **extra_kwargs,
                )

            # Check status
            if not 200 <= response.status_code < 300:
                return self._create_error_result(
                    f"API returned HTTP {response.status_code}",
                    url=url,
                    status_code=response.status_code,
                    response_text=response.text[:500],  # First 500 chars for debugging
                )

            # Parse JSON response
            try:
                json_data = response.json()
            except Exception as e:
                return self._create_error_result(
                    f"Failed to parse JSON response: {e}",
                    url=url,
                    status_code=response.status_code,
                    response_text=response.text[:500],
                )

            # Extract data using JSON path selectors
            extracted_data = {}
            if selectors:
                extracted_data = self.selector_processor.process_selectors(json_data, selectors)

            logger.info(
                "api_request_completed",
                url=url,
                status_code=response.status_code,
                extracted_fields=len(extracted_data),
            )

            return self._create_success_result(
                content=json_data,
                extracted_data=extracted_data,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

        except httpx.TimeoutException as e:
            return self._create_error_result(
                f"API request timeout: {e}",
                url=url,
                timeout=timeout,
            )
        except httpx.RequestError as e:
            return self._create_error_result(
                f"API request error: {e}",
                url=url,
            )
        except Exception as e:
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
            logger.debug("api_client_closed")
