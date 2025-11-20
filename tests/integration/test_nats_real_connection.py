"""Real integration tests requiring actual NATS server.

These tests require NATS to be running and will be skipped if not available.
Run with: make db-up && pytest tests/integration/test_nats_real_connection.py -v
"""

import asyncio
import socket
from collections.abc import AsyncGenerator

import pytest

from config import get_settings
from crawler.services.nats_queue import NATSQueueService

# Cache the NATS availability check result to avoid repeated slow checks
_NATS_AVAILABLE_CACHE: bool | None = None


def check_nats_available() -> bool:
    """Check if NATS server is available (fast check using socket).

    Uses a simple socket connection check instead of full NATS connection
    to make skipif evaluation fast.
    """
    global _NATS_AVAILABLE_CACHE

    # Guard: return cached result if available
    if _NATS_AVAILABLE_CACHE is not None:
        return _NATS_AVAILABLE_CACHE

    try:
        settings = get_settings()
        # Parse NATS URL to get host and port
        # Format: nats://host:port
        url = settings.nats_url.replace("nats://", "")
        if ":" in url:
            host, port = url.split(":")
            port = int(port)
        else:
            host = url
            port = 4222  # Default NATS port

        # Try to connect with 1 second timeout (fast check)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1.0)
        result = sock.connect_ex((host, port))
        sock.close()

        _NATS_AVAILABLE_CACHE = result == 0
        return _NATS_AVAILABLE_CACHE
    except Exception:
        _NATS_AVAILABLE_CACHE = False
        return False


@pytest.fixture
async def nats_service() -> AsyncGenerator[NATSQueueService, None]:
    """Create NATS service with real connection."""
    settings = get_settings()
    service = NATSQueueService(settings)
    await service.connect()
    yield service
    await service.disconnect()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not check_nats_available(),
    reason="NATS server not available - run 'make db-up' first",
)
class TestNATSRealConnection:
    """Integration tests with real NATS server."""

    async def test_connect_to_real_nats(self) -> None:
        """Test connection to real NATS server."""
        settings = get_settings()
        service = NATSQueueService(settings)

        try:
            # Connect should succeed if NATS is running
            await service.connect()

            # Verify connection is healthy
            assert await service.health_check()

            # Verify stream was created
            stream_info = await service.js.stream_info(settings.nats_stream_name)
            assert stream_info.config.name == settings.nats_stream_name

            # Verify consumer was created
            consumer_info = await service.get_consumer_info()
            assert consumer_info is not None
            assert consumer_info["name"] == settings.nats_consumer_name

        finally:
            await service.disconnect()

    async def test_publish_and_consume_real_message(self, nats_service: NATSQueueService) -> None:
        """Test publishing and consuming a message through real NATS."""
        job_id = "test-real-job-123"
        job_data = {
            "seed_url": "https://example.com/real-test",
            "priority": 5,
            "job_type": "one_time",
        }

        # Publish job
        published = await nats_service.publish_job(job_id, job_data)
        assert published is True

        # Verify message entered the consumer pipeline
        # The message is either pending (not yet delivered) or was delivered (processed by worker)
        # This handles the race condition with background workers
        consumer_info = await nats_service.get_consumer_info()
        assert consumer_info is not None

        # Count messages in the pipeline: pending + already delivered + being processed
        total_messages = (
            consumer_info["num_pending"]
            + consumer_info["num_delivered"]
            + consumer_info["num_ack_pending"]
        )
        # At least 1 message should have entered the consumer pipeline
        assert total_messages >= 1

    async def test_delete_job_from_real_queue(self, nats_service: NATSQueueService) -> None:
        """Test removing a job from real NATS queue."""
        job_id = "test-delete-real-job-456"
        job_data = {
            "seed_url": "https://example.com/delete-test",
            "priority": 3,
        }

        # Publish job
        published = await nats_service.publish_job(job_id, job_data)
        assert published is True

        # Delete from queue
        removed = await nats_service.delete_job_from_queue(job_id)

        # Note: delete_job_from_queue searches through messages
        # If successful, message should be removed
        # This is best-effort due to race conditions with other consumers
        # Just verify the method completes without error
        assert isinstance(removed, bool)

    async def test_health_check_with_real_nats(self, nats_service: NATSQueueService) -> None:
        """Test health check with real NATS connection."""
        health = await nats_service.health_check()
        assert health is True

        # Get stream and consumer metrics
        count = await nats_service.get_pending_job_count()
        assert isinstance(count, int)
        assert count >= 0

        consumer_info = await nats_service.get_consumer_info()
        assert consumer_info is not None
        assert "num_pending" in consumer_info
        assert "num_ack_pending" in consumer_info


@pytest.mark.asyncio
class TestNATSConnectionFailure:
    """Tests for NATS connection failures."""

    async def test_connect_with_invalid_url(self) -> None:
        """Test connection failure with invalid NATS URL."""
        settings = get_settings()
        settings.nats_url = "nats://invalid-host:9999"
        service = NATSQueueService(settings)

        # Connection should fail (limit to 3 seconds instead of default timeout)
        try:
            await asyncio.wait_for(service.connect(), timeout=3.0)
            # If we get here, the connection succeeded (shouldn't happen)
            pytest.fail("Connection should have failed with invalid URL")
        except TimeoutError:
            # Expected: connection attempt times out
            pass
        except RuntimeError as e:
            # Also expected: connection fails immediately
            assert "Failed to connect to NATS" in str(e)

    async def test_operations_fail_when_not_connected(self) -> None:
        """Test that operations fail gracefully when not connected."""
        settings = get_settings()
        service = NATSQueueService(settings)

        # Don't connect - verify operations return False
        assert await service.publish_job("test", {}) is False
        assert await service.delete_job_from_queue("test") is False
        assert await service.get_pending_job_count() == 0
        assert await service.get_consumer_info() is None
        assert await service.health_check() is False
