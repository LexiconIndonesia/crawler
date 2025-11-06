"""Unit tests for resource cleanup service."""

import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from crawler.services.resource_cleanup import (
    BrowserResourceManager,
    CleanupCoordinator,
    HTTPResourceManager,
)


class TestHTTPResourceManager:
    """Tests for HTTPResourceManager."""

    async def test_tracked_request_increments_and_decrements(self) -> None:
        """Test that tracked_request properly tracks active requests."""
        client = Mock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        assert manager._active_requests == 0

        async with manager.tracked_request():
            assert manager._active_requests == 1

        assert manager._active_requests == 0

    async def test_tracked_request_handles_exceptions(self) -> None:
        """Test that tracked_request decrements counter even on exception."""
        client = Mock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        with pytest.raises(ValueError):
            async with manager.tracked_request():
                assert manager._active_requests == 1
                raise ValueError("test error")

        assert manager._active_requests == 0

    async def test_close_gracefully_success(self) -> None:
        """Test graceful close when no requests are active."""
        client = AsyncMock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        result = await manager.close_gracefully(timeout_seconds=5.0)

        assert result is True
        client.aclose.assert_called_once()

    async def test_close_gracefully_waits_for_requests(self) -> None:
        """Test graceful close waits for active requests to complete."""
        client = AsyncMock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        # Simulate an active request that completes after a delay
        async def simulate_request() -> None:
            async with manager.tracked_request():
                await asyncio.sleep(0.2)

        # Start a background request
        task = asyncio.create_task(simulate_request())

        # Wait a bit to ensure request is active
        await asyncio.sleep(0.1)
        assert manager._active_requests == 1

        # Try to close gracefully
        result = await manager.close_gracefully(timeout_seconds=1.0)

        await task  # Clean up task

        assert result is True
        client.aclose.assert_called_once()

    async def test_close_gracefully_timeout(self) -> None:
        """Test graceful close times out if requests take too long."""
        client = AsyncMock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        # Simulate a long-running request
        async def simulate_long_request() -> None:
            async with manager.tracked_request():
                await asyncio.sleep(2.0)

        # Start a background request
        task = asyncio.create_task(simulate_long_request())

        # Wait a bit to ensure request is active
        await asyncio.sleep(0.1)

        # Try to close gracefully with short timeout
        result = await manager.close_gracefully(timeout_seconds=0.2)

        assert result is False
        client.aclose.assert_not_called()

        # Clean up
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def test_force_close(self) -> None:
        """Test force close immediately closes client."""
        client = AsyncMock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        # Simulate active requests
        manager._active_requests = 3

        await manager.force_close()

        client.aclose.assert_called_once()

    async def test_is_active(self) -> None:
        """Test is_active returns correct status."""
        client = Mock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        assert manager.is_active() is False

        async with manager.tracked_request():
            assert manager.is_active() is True

        assert manager.is_active() is False

    async def test_is_active_false_when_closing(self) -> None:
        """Test is_active returns False when closing flag is set."""
        client = Mock(spec=httpx.AsyncClient)
        manager = HTTPResourceManager(client)

        manager._active_requests = 1
        manager._closing = True

        assert manager.is_active() is False


class TestBrowserResourceManager:
    """Tests for BrowserResourceManager."""

    async def test_close_gracefully_no_contexts(self) -> None:
        """Test graceful close with no browser contexts."""
        manager = BrowserResourceManager(contexts=[])

        result = await manager.close_gracefully(timeout_seconds=5.0)

        assert result is True

    async def test_close_gracefully_with_contexts(self) -> None:
        """Test graceful close with browser contexts."""
        # Mock browser contexts with close method
        context1 = AsyncMock()
        context2 = AsyncMock()
        manager = BrowserResourceManager(contexts=[context1, context2])

        result = await manager.close_gracefully(timeout_seconds=5.0)

        assert result is True
        context1.close.assert_called_once()
        context2.close.assert_called_once()

    async def test_close_gracefully_timeout(self) -> None:
        """Test graceful close times out for slow contexts."""

        async def slow_close() -> None:
            await asyncio.sleep(2.0)

        context = AsyncMock()
        context.close = slow_close
        manager = BrowserResourceManager(contexts=[context])

        result = await manager.close_gracefully(timeout_seconds=0.1)

        assert result is False

    async def test_force_close(self) -> None:
        """Test force close closes all contexts."""
        context1 = AsyncMock()
        context2 = AsyncMock()
        manager = BrowserResourceManager(contexts=[context1, context2])

        await manager.force_close()

        context1.close.assert_called_once()
        context2.close.assert_called_once()

    async def test_force_close_handles_errors(self) -> None:
        """Test force close continues even if context close fails."""
        context1 = AsyncMock()
        context1.close.side_effect = Exception("close failed")
        context2 = AsyncMock()
        manager = BrowserResourceManager(contexts=[context1, context2])

        await manager.force_close()

        # Both should be called despite error in first
        context1.close.assert_called_once()
        context2.close.assert_called_once()

    async def test_is_active(self) -> None:
        """Test is_active returns correct status."""
        manager = BrowserResourceManager(contexts=[])
        assert manager.is_active() is False

        manager = BrowserResourceManager(contexts=[Mock(), Mock()])
        assert manager.is_active() is True

        manager._closing = True
        assert manager.is_active() is False


class TestCleanupCoordinator:
    """Tests for CleanupCoordinator."""

    async def test_register_resource(self) -> None:
        """Test resource registration."""
        coordinator = CleanupCoordinator()
        resource = Mock(spec=HTTPResourceManager)

        coordinator.register_resource(resource)

        assert len(coordinator.resources) == 1
        assert coordinator.resources[0] is resource

    async def test_cleanup_all_graceful_success(self) -> None:
        """Test cleanup when all resources close gracefully."""
        coordinator = CleanupCoordinator(graceful_timeout=5.0)

        # Mock resources that close gracefully
        resource1 = AsyncMock(spec=HTTPResourceManager)
        resource1.close_gracefully.return_value = True
        resource2 = AsyncMock(spec=BrowserResourceManager)
        resource2.close_gracefully.return_value = True

        coordinator.register_resource(resource1)
        coordinator.register_resource(resource2)

        metadata = await coordinator.cleanup_all(
            job_id="test-job-123",
            cancelled_by="user-456",
            reason="test cancellation",
        )

        assert metadata["total_resources"] == 2
        assert len(metadata["graceful_close_succeeded"]) == 2
        assert len(metadata["force_closed"]) == 0
        assert metadata["cancelled_by"] == "user-456"
        assert metadata["cancellation_reason"] == "test cancellation"

        resource1.close_gracefully.assert_called_once()
        resource1.force_close.assert_not_called()
        resource2.close_gracefully.assert_called_once()
        resource2.force_close.assert_not_called()

    async def test_cleanup_all_force_close_on_timeout(self) -> None:
        """Test cleanup force closes resources that timeout."""
        coordinator = CleanupCoordinator(graceful_timeout=0.1)

        # Mock resource that fails graceful close
        resource = AsyncMock(spec=HTTPResourceManager)
        resource.close_gracefully.return_value = False

        coordinator.register_resource(resource)

        metadata = await coordinator.cleanup_all(
            job_id="test-job-123",
        )

        assert metadata["total_resources"] == 1
        assert len(metadata["graceful_close_succeeded"]) == 0
        assert len(metadata["force_closed"]) == 1

        resource.close_gracefully.assert_called_once()
        resource.force_close.assert_called_once()

    async def test_cleanup_all_handles_exceptions(self) -> None:
        """Test cleanup continues despite resource errors."""
        coordinator = CleanupCoordinator()

        # Resource that raises exception during graceful close
        resource1 = AsyncMock(spec=HTTPResourceManager)
        resource1.close_gracefully.side_effect = Exception("close failed")

        # Resource that closes normally
        resource2 = AsyncMock(spec=HTTPResourceManager)
        resource2.close_gracefully.return_value = True

        coordinator.register_resource(resource1)
        coordinator.register_resource(resource2)

        metadata = await coordinator.cleanup_all(job_id="test-job-123")

        assert metadata["total_resources"] == 2
        # resource1 should be force closed, resource2 gracefully closed
        assert len(metadata["force_closed"]) == 1
        assert len(metadata["graceful_close_succeeded"]) == 1

        resource1.force_close.assert_called_once()
        resource2.force_close.assert_not_called()

    async def test_cleanup_and_update_job_success(self) -> None:
        """Test cleanup with successful job status update."""
        coordinator = CleanupCoordinator()
        resource = AsyncMock(spec=HTTPResourceManager)
        resource.close_gracefully.return_value = True
        coordinator.register_resource(resource)

        # Mock job repository
        job_repo = AsyncMock()
        mock_job = Mock()
        mock_job.cancelled_at = None
        job_repo.cancel.return_value = mock_job

        metadata = await coordinator.cleanup_and_update_job(
            job_id="test-job-123",
            job_repo=job_repo,
            cancelled_by="user-456",
            reason="test reason",
        )

        assert metadata["job_status_updated"] is True
        job_repo.cancel.assert_called_once_with(
            job_id="test-job-123",
            cancelled_by="user-456",
            reason="test reason",
        )

    async def test_cleanup_and_update_job_repo_failure(self) -> None:
        """Test cleanup when job repository update fails."""
        coordinator = CleanupCoordinator()
        resource = AsyncMock(spec=HTTPResourceManager)
        resource.close_gracefully.return_value = True
        coordinator.register_resource(resource)

        # Mock job repository that fails
        job_repo = AsyncMock()
        job_repo.cancel.side_effect = Exception("database error")

        metadata = await coordinator.cleanup_and_update_job(
            job_id="test-job-123",
            job_repo=job_repo,
        )

        assert metadata["job_status_updated"] is False
        assert "job_status_update_error" in metadata
        assert "database error" in metadata["job_status_update_error"]

    async def test_cleanup_and_update_job_returns_none(self) -> None:
        """Test cleanup when job repository returns None."""
        coordinator = CleanupCoordinator()
        resource = AsyncMock(spec=HTTPResourceManager)
        resource.close_gracefully.return_value = True
        coordinator.register_resource(resource)

        # Mock job repository that returns None (job not found/already cancelled)
        job_repo = AsyncMock()
        job_repo.cancel.return_value = None

        metadata = await coordinator.cleanup_and_update_job(
            job_id="test-job-123",
            job_repo=job_repo,
        )

        assert metadata["job_status_updated"] is False
        job_repo.cancel.assert_called_once()
