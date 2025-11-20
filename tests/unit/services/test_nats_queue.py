"""Unit tests for NATS queue service."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from config import Settings
from crawler.services.nats_queue import NATSQueueService


@pytest.fixture
def settings() -> Settings:
    """Create settings for testing."""
    return Settings(
        nats_url="nats://localhost:4222",
        nats_stream_name="TEST_STREAM",
        nats_consumer_name="test-consumer",
    )


@pytest.fixture
def nats_service(settings: Settings) -> NATSQueueService:
    """Create NATS queue service for testing."""
    return NATSQueueService(settings)


class TestNATSQueueService:
    """Tests for NATSQueueService."""

    async def test_initialization(self, settings: Settings) -> None:
        """Test service initialization."""
        service = NATSQueueService(settings)

        assert service.settings == settings
        assert service.client is None
        assert service.js is None
        assert service.stream_name == "TEST_STREAM"
        assert service.consumer_name == "test-consumer"

    @patch("crawler.services.nats_queue.nats.connect")
    async def test_connect_success(
        self,
        mock_connect: AsyncMock,
        nats_service: NATSQueueService,
    ) -> None:
        """Test successful connection to NATS."""
        # Mock NATS client (use MagicMock since jetstream() is not async)
        mock_client = MagicMock()
        mock_js = AsyncMock()

        # jetstream() returns synchronously in nats-py
        mock_client.jetstream.return_value = mock_js
        mock_connect.return_value = mock_client

        # Mock stream and consumer info calls
        mock_js.stream_info = AsyncMock()
        mock_js.update_stream = AsyncMock()
        mock_js.consumer_info = AsyncMock()
        mock_js.add_stream = AsyncMock()
        mock_js.add_consumer = AsyncMock()

        await nats_service.connect()

        # Verify client is connected
        assert nats_service.client == mock_client
        assert nats_service.js == mock_js
        mock_connect.assert_called_once_with(nats_service.settings.nats_url)

    @patch("crawler.services.nats_queue.nats.connect")
    async def test_connect_failure(
        self,
        mock_connect: AsyncMock,
        nats_service: NATSQueueService,
    ) -> None:
        """Test connection failure."""
        mock_connect.side_effect = Exception("Connection failed")

        with pytest.raises(RuntimeError, match="Failed to connect to NATS"):
            await nats_service.connect()

    async def test_disconnect_when_connected(self, nats_service: NATSQueueService) -> None:
        """Test disconnect when client is connected."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        nats_service.client = mock_client

        await nats_service.disconnect()

        mock_client.drain.assert_called_once()
        mock_client.close.assert_called_once()

    async def test_disconnect_when_not_connected(self, nats_service: NATSQueueService) -> None:
        """Test disconnect when client is not connected."""
        nats_service.client = None

        # Should not raise any errors
        await nats_service.disconnect()

    async def test_publish_job_success(self, nats_service: NATSQueueService) -> None:
        """Test successful job publishing."""
        mock_js = AsyncMock()
        mock_ack = MagicMock()
        mock_ack.stream = "TEST_STREAM"
        mock_ack.seq = 123
        mock_js.publish.return_value = mock_ack
        nats_service.js = mock_js

        job_id = "test-job-123"
        job_data = {"seed_url": "https://example.com", "priority": 5}

        result = await nats_service.publish_job(job_id, job_data)

        assert result is True
        mock_js.publish.assert_called_once()

        # Verify call arguments
        call_args = mock_js.publish.call_args
        assert call_args[0][0] == "TEST_STREAM.jobs"  # subject
        assert job_id in call_args[0][1].decode("utf-8")  # payload contains job_id
        assert call_args[1]["headers"]["Nats-Msg-Id"] == job_id  # deduplication header

    async def test_publish_job_not_connected(self, nats_service: NATSQueueService) -> None:
        """Test publishing when not connected."""
        nats_service.js = None

        result = await nats_service.publish_job("test-job", {})

        assert result is False

    async def test_publish_job_failure(self, nats_service: NATSQueueService) -> None:
        """Test publish failure."""
        mock_js = AsyncMock()
        mock_js.publish.side_effect = Exception("Publish failed")
        nats_service.js = mock_js

        result = await nats_service.publish_job("test-job", {})

        assert result is False

    async def test_delete_job_from_queue_not_connected(
        self, nats_service: NATSQueueService
    ) -> None:
        """Test delete when not connected."""
        nats_service.js = None

        result = await nats_service.delete_job_from_queue("test-job")

        assert result is False

    async def test_get_pending_job_count_success(self, nats_service: NATSQueueService) -> None:
        """Test getting pending job count."""
        mock_js = AsyncMock()
        mock_stream_info = MagicMock()
        mock_stream_info.state.messages = 42
        mock_js.stream_info.return_value = mock_stream_info
        nats_service.js = mock_js

        count = await nats_service.get_pending_job_count()

        assert count == 42
        mock_js.stream_info.assert_called_once_with("TEST_STREAM")

    async def test_get_pending_job_count_not_connected(
        self, nats_service: NATSQueueService
    ) -> None:
        """Test get count when not connected."""
        nats_service.js = None

        count = await nats_service.get_pending_job_count()

        assert count == 0

    async def test_get_consumer_info_success(self, nats_service: NATSQueueService) -> None:
        """Test getting consumer info."""
        mock_js = AsyncMock()
        mock_consumer_info = MagicMock()
        mock_consumer_info.name = "test-consumer"
        mock_consumer_info.num_pending = 10
        mock_consumer_info.num_redelivered = 2
        mock_consumer_info.num_waiting = 0
        mock_consumer_info.num_ack_pending = 3
        mock_consumer_info.delivered.consumer_seq = 15
        mock_js.consumer_info.return_value = mock_consumer_info
        nats_service.js = mock_js

        info = await nats_service.get_consumer_info()

        assert info is not None
        assert info["name"] == "test-consumer"
        assert info["num_pending"] == 10
        assert info["num_redelivered"] == 2
        assert info["num_waiting"] == 0
        assert info["num_ack_pending"] == 3
        assert info["num_delivered"] == 15

    async def test_get_consumer_info_not_connected(self, nats_service: NATSQueueService) -> None:
        """Test get consumer info when not connected."""
        nats_service.js = None

        info = await nats_service.get_consumer_info()

        assert info is None

    async def test_health_check_healthy(self, nats_service: NATSQueueService) -> None:
        """Test health check when healthy."""
        mock_client = AsyncMock()
        mock_client.is_closed = False
        mock_js = AsyncMock()
        mock_js.stream_info = AsyncMock()
        nats_service.client = mock_client
        nats_service.js = mock_js

        result = await nats_service.health_check()

        assert result is True

    async def test_health_check_not_connected(self, nats_service: NATSQueueService) -> None:
        """Test health check when not connected."""
        nats_service.client = None

        result = await nats_service.health_check()

        assert result is False

    async def test_health_check_client_closed(self, nats_service: NATSQueueService) -> None:
        """Test health check when client is closed."""
        mock_client = AsyncMock()
        mock_client.is_closed = True
        nats_service.client = mock_client

        result = await nats_service.health_check()

        assert result is False
