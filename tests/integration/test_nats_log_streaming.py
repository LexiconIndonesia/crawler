"""Integration tests for NATS-based real-time log streaming."""

import asyncio
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from config import get_settings
from crawler.api.websocket_models import WebSocketLogMessage
from crawler.db.generated.models import LogLevelEnum
from crawler.db.repositories import CrawlJobRepository, CrawlLogRepository, WebsiteRepository
from crawler.services.log_publisher import LogPublisher
from crawler.services.nats_queue import NATSQueueService


@pytest.mark.asyncio
class TestNATSLogStreaming:
    """Test NATS-based real-time log streaming."""

    async def test_log_publisher_publishes_to_nats(
        self,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that logs are published to NATS after DB insert."""
        settings = get_settings()

        # Create website and job first (foreign key requirements)
        website_repo = WebsiteRepository(db_connection)
        website = await website_repo.create(
            name="Test Website - Publish",
            base_url="https://example.com",
            config={},
        )
        assert website

        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create(
            website_id=website.id,
            seed_url="https://example.com",
        )
        assert job

        job_id = job.id
        website_id = website.id

        # Setup NATS
        nats_service = NATSQueueService(settings)
        await nats_service.connect()

        try:
            # Create log publisher with NATS client
            log_publisher = LogPublisher(nats_client=nats_service.client)
            assert log_publisher.is_enabled

            # Create repository with log publisher
            log_repo = CrawlLogRepository(db_connection, log_publisher=log_publisher)

            # Subscribe to NATS subject before creating log
            subject = f"logs.{job_id}"
            subscription = await nats_service.client.subscribe(subject)

            # Create log (should be published to NATS)
            log = await log_repo.create(
                job_id=job_id,
                website_id=website_id,
                message="Test log message",
                log_level=LogLevelEnum.INFO,
                step_name="test_step",
                context={"test_key": "test_value"},
            )

            assert log is not None

            # Receive message from NATS
            try:
                msg = await asyncio.wait_for(subscription.next_msg(), timeout=2.0)
                payload = json.loads(msg.data.decode("utf-8"))

                # Verify message format
                ws_message = WebSocketLogMessage(**payload)
                assert ws_message.id == log.id
                assert ws_message.job_id == str(log.job_id)
                assert ws_message.message == "Test log message"
                assert ws_message.log_level == "INFO"
                assert ws_message.step_name == "test_step"
                assert ws_message.context == {"test_key": "test_value"}

            except TimeoutError:
                pytest.fail("No message received from NATS within 2 seconds")

            # Cleanup
            await subscription.unsubscribe()

        finally:
            await nats_service.disconnect()

    async def test_log_publisher_graceful_degradation(
        self,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that logs are still saved to DB when NATS is unavailable."""
        # Create website and job first
        website_repo = WebsiteRepository(db_connection)
        website = await website_repo.create(
            name="Test Website - Degradation",
            base_url="https://example.com",
            config={},
        )

        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create(
            website_id=website.id,
            seed_url="https://example.com",
        )

        job_id = job.id
        website_id = website.id

        # Create log publisher without NATS client (disabled)
        log_publisher = LogPublisher(nats_client=None)
        assert not log_publisher.is_enabled

        # Create repository with disabled log publisher
        log_repo = CrawlLogRepository(db_connection, log_publisher=log_publisher)

        # Create log (should succeed despite NATS being unavailable)
        log = await log_repo.create(
            job_id=job_id,
            website_id=website_id,
            message="Test log without NATS",
            log_level=LogLevelEnum.WARNING,
        )

        # Verify log was saved to database
        assert log is not None
        assert log.message == "Test log without NATS"
        assert log.log_level == LogLevelEnum.WARNING

        # Verify we can retrieve it from DB
        logs = await log_repo.list_by_job(job_id=job_id, limit=10)
        assert len(logs) == 1
        assert logs[0].id == log.id

    async def test_multiple_logs_batch_publishing(
        self,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that multiple logs are published to NATS in sequence."""
        settings = get_settings()

        # Create website and job first
        website_repo = WebsiteRepository(db_connection)
        website = await website_repo.create(
            name="Test Website - Batch",
            base_url="https://example.com",
            config={},
        )

        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create(
            website_id=website.id,
            seed_url="https://example.com",
        )

        job_id = job.id
        website_id = website.id

        # Setup NATS
        nats_service = NATSQueueService(settings)
        await nats_service.connect()

        try:
            # Create log publisher
            log_publisher = LogPublisher(nats_client=nats_service.client)
            log_repo = CrawlLogRepository(db_connection, log_publisher=log_publisher)

            # Subscribe to NATS subject
            subject = f"logs.{job_id}"
            subscription = await nats_service.client.subscribe(subject)

            # Create multiple logs
            log_messages = ["Log message 1", "Log message 2", "Log message 3"]
            created_logs = []

            for message in log_messages:
                log = await log_repo.create(
                    job_id=job_id,
                    website_id=website_id,
                    message=message,
                    log_level=LogLevelEnum.INFO,
                )
                created_logs.append(log)

            # Receive all messages from NATS
            received_messages = []
            for _ in range(len(log_messages)):
                try:
                    msg = await asyncio.wait_for(subscription.next_msg(), timeout=2.0)
                    payload = json.loads(msg.data.decode("utf-8"))
                    ws_message = WebSocketLogMessage(**payload)
                    received_messages.append(ws_message)
                except TimeoutError:
                    pytest.fail(
                        f"Only received {len(received_messages)} of {len(log_messages)} messages"
                    )

            # Verify all messages were received
            assert len(received_messages) == len(log_messages)
            received_texts = [msg.message for msg in received_messages]
            assert received_texts == log_messages

            # Cleanup
            await subscription.unsubscribe()

        finally:
            await nats_service.disconnect()

    async def test_log_publisher_disable_enable(
        self,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that log publishing can be disabled and re-enabled."""
        settings = get_settings()

        # Create website and job first
        website_repo = WebsiteRepository(db_connection)
        website = await website_repo.create(
            name="Test Website - Toggle",
            base_url="https://example.com",
            config={},
        )

        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create(
            website_id=website.id,
            seed_url="https://example.com",
        )

        job_id = job.id
        website_id = website.id

        # Setup NATS
        nats_service = NATSQueueService(settings)
        await nats_service.connect()

        try:
            # Create log publisher
            log_publisher = LogPublisher(nats_client=nats_service.client)
            log_repo = CrawlLogRepository(db_connection, log_publisher=log_publisher)

            # Subscribe to NATS subject
            subject = f"logs.{job_id}"
            subscription = await nats_service.client.subscribe(subject)

            # Disable publishing
            log_publisher.disable()
            assert not log_publisher.is_enabled

            # Create log while disabled (should NOT be published)
            await log_repo.create(
                job_id=job_id,
                website_id=website_id,
                message="Message while disabled",
                log_level=LogLevelEnum.INFO,
            )

            # Verify no message received
            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(subscription.next_msg(), timeout=0.5)

            # Re-enable publishing
            log_publisher.enable()
            assert log_publisher.is_enabled

            # Create log while enabled (should be published)
            await log_repo.create(
                job_id=job_id,
                website_id=website_id,
                message="Message while enabled",
                log_level=LogLevelEnum.INFO,
            )

            # Verify message received
            msg = await asyncio.wait_for(subscription.next_msg(), timeout=2.0)
            payload = json.loads(msg.data.decode("utf-8"))
            ws_message = WebSocketLogMessage(**payload)
            assert ws_message.message == "Message while enabled"

            # Cleanup
            await subscription.unsubscribe()

        finally:
            await nats_service.disconnect()
