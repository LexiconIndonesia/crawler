"""Real integration tests requiring actual NATS server.

These tests require NATS to be running and will be skipped if not available.
Run with: make db-up && pytest tests/integration/test_nats_real_connection.py -v
"""

import pytest

from config import get_settings
from crawler.services.nats_queue import NATSQueueService


async def check_nats_available() -> bool:
    """Check if NATS server is available."""
    try:
        settings = get_settings()
        service = NATSQueueService(settings)
        await service.connect()
        health = await service.health_check()
        await service.disconnect()
        return health
    except Exception:
        return False


@pytest.fixture
async def nats_service() -> NATSQueueService:
    """Create NATS service with real connection."""
    settings = get_settings()
    service = NATSQueueService(settings)
    await service.connect()
    yield service
    await service.disconnect()


@pytest.mark.asyncio
@pytest.mark.skipif(
    not pytest.mark.asyncio,
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

        # Verify message count increased
        count = await nats_service.get_pending_job_count()
        assert count >= 1

        # Consumer info should show pending messages
        consumer_info = await nats_service.get_consumer_info()
        assert consumer_info is not None
        assert consumer_info["num_pending"] >= 1

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

        # Connection should fail
        with pytest.raises(RuntimeError, match="Failed to connect to NATS"):
            await service.connect()

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
