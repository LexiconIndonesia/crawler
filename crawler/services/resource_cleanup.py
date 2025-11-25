"""Resource cleanup service for graceful cancellation handling.

This module provides infrastructure for cleaning up resources (HTTP connections,
browser contexts, etc.) when a crawl job is cancelled. It implements:
- Graceful shutdown with configurable timeout
- Force close for unresponsive resources
- Partial result preservation
- Job status updates with cancellation metadata
"""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import httpx

from crawler.core.logging import get_logger

if TYPE_CHECKING:
    from crawler.db.repositories import CrawlJobRepository

logger = get_logger(__name__)


class ResourceManager(ABC):
    """Abstract base class for managing crawl resources.

    Resource managers handle the lifecycle of resources like HTTP connections
    and browser contexts, providing graceful shutdown and force close capabilities.
    """

    @abstractmethod
    async def close_gracefully(self, timeout_seconds: float = 5.0) -> bool:
        """Attempt to close resource gracefully within timeout.

        Args:
            timeout_seconds: Maximum time to wait for graceful closure

        Returns:
            True if closed gracefully, False if timeout exceeded
        """
        pass

    @abstractmethod
    async def force_close(self) -> None:
        """Force close the resource immediately."""
        pass

    @abstractmethod
    def is_active(self) -> bool:
        """Check if resource is currently active.

        Returns:
            True if resource has ongoing operations
        """
        pass


class HTTPResourceManager(ResourceManager):
    """Manages HTTP client resources with graceful shutdown.

    Wraps httpx.AsyncClient to provide:
    - Abort capability for ongoing requests
    - Graceful shutdown with timeout
    - Force close mechanism
    """

    def __init__(self, client: httpx.AsyncClient):
        """Initialize HTTP resource manager.

        Args:
            client: The httpx AsyncClient to manage
        """
        self.client = client
        self._active_requests = 0
        self._closing = False

    @asynccontextmanager
    async def tracked_request(self) -> Any:
        """Context manager to track active HTTP requests.

        Usage:
            async with manager.tracked_request():
                response = await manager.client.get(url)
        """
        self._active_requests += 1
        try:
            yield
        finally:
            self._active_requests -= 1

    async def close_gracefully(self, timeout_seconds: float = 5.0) -> bool:
        """Wait for active requests to complete, then close client.

        Args:
            timeout_seconds: Maximum time to wait for active requests

        Returns:
            True if all requests completed within timeout, False otherwise
        """
        self._closing = True
        logger.info("http_resource_graceful_close_started", timeout=timeout_seconds)

        try:
            # Wait for active requests to complete
            start_time = asyncio.get_event_loop().time()
            while self._active_requests > 0:
                elapsed = asyncio.get_event_loop().time() - start_time
                remaining = timeout_seconds - elapsed

                if remaining <= 0:
                    logger.warning(
                        "http_resource_graceful_close_timeout",
                        active_requests=self._active_requests,
                    )
                    return False

                # Check every 100ms
                await asyncio.sleep(0.1)

            # All requests completed, close client
            await self.client.aclose()
            logger.info("http_resource_closed_gracefully")
            return True

        except Exception as e:
            logger.error("http_resource_graceful_close_error", error=str(e))
            return False

    async def force_close(self) -> None:
        """Force close HTTP client immediately, aborting active requests."""
        try:
            logger.warning("http_resource_force_close", active_requests=self._active_requests)
            await self.client.aclose()
            logger.info("http_resource_force_closed")
        except Exception as e:
            logger.error("http_resource_force_close_error", error=str(e))

    def is_active(self) -> bool:
        """Check if there are active HTTP requests.

        Returns:
            True if requests are in progress
        """
        return self._active_requests > 0 and not self._closing


class BrowserResourceManager(ResourceManager):
    """Manages browser context resources (Playwright, Selenium, etc.).

    Placeholder for future browser automation integration.
    Provides graceful shutdown for browser contexts.
    """

    def __init__(self, contexts: list[Any] | None = None):
        """Initialize browser resource manager.

        Args:
            contexts: List of browser contexts to manage
        """
        self.contexts = contexts or []
        self._closing = False

    async def close_gracefully(self, timeout_seconds: float = 5.0) -> bool:
        """Close all browser contexts gracefully.

        Args:
            timeout_seconds: Maximum time to wait for contexts to close

        Returns:
            True if all contexts closed within timeout, False otherwise
        """
        if not self.contexts:
            return True

        self._closing = True
        logger.info("browser_resource_graceful_close_started", count=len(self.contexts))

        try:
            # Close all contexts with timeout
            close_tasks = [self._close_context(ctx) for ctx in self.contexts]
            await asyncio.wait_for(
                asyncio.gather(*close_tasks, return_exceptions=True),
                timeout=timeout_seconds,
            )
            logger.info("browser_resource_closed_gracefully")
            return True

        except TimeoutError:
            logger.warning("browser_resource_graceful_close_timeout")
            return False
        except Exception as e:
            logger.error("browser_resource_graceful_close_error", error=str(e))
            return False

    async def force_close(self) -> None:
        """Force close all browser contexts immediately."""
        try:
            logger.warning("browser_resource_force_close", count=len(self.contexts))
            # Force close all contexts without waiting
            for ctx in self.contexts:
                try:
                    await self._close_context(ctx)
                except Exception as e:
                    logger.error("browser_context_force_close_error", error=str(e))
            logger.info("browser_resource_force_closed")
        except Exception as e:
            logger.error("browser_resource_force_close_error", error=str(e))

    def is_active(self) -> bool:
        """Check if there are active browser contexts.

        Returns:
            True if contexts exist and not closing
        """
        return len(self.contexts) > 0 and not self._closing

    async def _close_context(self, context: Any) -> None:
        """Close a single browser context.

        Args:
            context: Browser context to close
        """
        # Placeholder - actual implementation depends on browser automation library
        # For Playwright: await context.close()
        # For Selenium: context.quit()
        if hasattr(context, "close"):
            await context.close()
        elif hasattr(context, "quit"):
            context.quit()


class CleanupCoordinator:
    """Coordinates resource cleanup during job cancellation.

    Orchestrates:
    1. Graceful shutdown of all resources (5s timeout)
    2. Force close if timeout exceeded
    3. Partial result preservation
    4. Job status update with cancellation metadata
    """

    def __init__(
        self,
        graceful_timeout: float = 5.0,
    ):
        """Initialize cleanup coordinator.

        Args:
            graceful_timeout: Seconds to wait for graceful shutdown
        """
        self.graceful_timeout = graceful_timeout
        self.resources: list[ResourceManager] = []

    def register_resource(self, resource: ResourceManager) -> None:
        """Register a resource for cleanup tracking.

        Args:
            resource: Resource manager to track
        """
        self.resources.append(resource)
        logger.debug("resource_registered", resource_type=type(resource).__name__)

    async def cleanup_all(
        self,
        job_id: str,
        cancelled_by: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Clean up all registered resources and return cleanup metadata.

        Args:
            job_id: Job ID being cancelled
            cancelled_by: User/system that cancelled the job
            reason: Cancellation reason

        Returns:
            Dictionary with cleanup metadata (timestamps, graceful flags, etc.)
        """
        logger.info(
            "cleanup_started",
            job_id=job_id,
            resource_count=len(self.resources),
            cancelled_by=cancelled_by,
            reason=reason,
        )

        cleanup_start = datetime.now(UTC)
        graceful_close_succeeded = []
        force_closed = []

        # Phase 1: Attempt graceful close for all resources concurrently
        # This ensures total cleanup time is max(timeouts) not sum(timeouts)
        graceful_tasks = [
            resource.close_gracefully(self.graceful_timeout) for resource in self.resources
        ]
        results = await asyncio.gather(*graceful_tasks, return_exceptions=True)

        # Phase 2: Handle results and force close failures
        for resource, result in zip(self.resources, results, strict=False):
            resource_type = type(resource).__name__

            if isinstance(result, Exception):
                # Exception during graceful close, force close as fallback
                logger.error(
                    "resource_cleanup_error",
                    resource_type=resource_type,
                    error=str(result),
                    exc_info=True,
                )
                try:
                    await resource.force_close()
                    force_closed.append(resource_type)
                except Exception as force_error:
                    logger.error(
                        "resource_force_close_failed",
                        resource_type=resource_type,
                        error=str(force_error),
                    )

            elif not result:
                # Graceful close timed out, proceed to force close
                logger.warning("resource_force_closed_after_timeout", resource_type=resource_type)
                try:
                    await resource.force_close()
                    force_closed.append(resource_type)
                except Exception as force_error:
                    logger.error(
                        "resource_force_close_failed",
                        resource_type=resource_type,
                        error=str(force_error),
                    )

            else:
                # Graceful close succeeded
                graceful_close_succeeded.append(resource_type)
                logger.info("resource_closed_gracefully", resource_type=resource_type)

        cleanup_end = datetime.now(UTC)
        cleanup_duration = (cleanup_end - cleanup_start).total_seconds()

        metadata = {
            "cleanup_started_at": cleanup_start.isoformat(),
            "cleanup_completed_at": cleanup_end.isoformat(),
            "cleanup_duration_seconds": cleanup_duration,
            "graceful_close_succeeded": graceful_close_succeeded,
            "force_closed": force_closed,
            "total_resources": len(self.resources),
            "cancelled_by": cancelled_by,
            "cancellation_reason": reason,
        }

        logger.info(
            "cleanup_completed",
            job_id=job_id,
            duration=cleanup_duration,
            graceful_count=len(graceful_close_succeeded),
            force_count=len(force_closed),
        )

        return metadata

    async def cleanup_and_update_job(
        self,
        job_id: str,
        job_repo: CrawlJobRepository,
        cancelled_by: str | None = None,
        reason: str | None = None,
    ) -> dict[str, Any]:
        """Clean up resources and update job status in database.

        Args:
            job_id: Job ID being cancelled
            job_repo: CrawlJobRepository instance for DB updates
            cancelled_by: User/system that cancelled the job
            reason: Cancellation reason

        Returns:
            Cleanup metadata dictionary
        """
        # Perform cleanup
        metadata = await self.cleanup_all(
            job_id=job_id,
            cancelled_by=cancelled_by,
            reason=reason,
        )

        # Update job status in database
        try:
            updated_job = await job_repo.cancel(
                job_id=job_id,
                cancelled_by=cancelled_by,
                reason=reason,
            )

            if updated_job:
                logger.info("job_status_updated_to_cancelled", job_id=job_id)
                metadata["job_status_updated"] = True
                metadata["job_cancelled_at"] = (
                    updated_job.cancelled_at.isoformat() if updated_job.cancelled_at else None
                )
            else:
                logger.warning("job_status_update_failed", job_id=job_id)
                metadata["job_status_updated"] = False

        except Exception as e:
            logger.error(
                "job_status_update_error",
                job_id=job_id,
                error=str(e),
                exc_info=True,
            )
            metadata["job_status_updated"] = False
            metadata["job_status_update_error"] = str(e)

        return metadata
