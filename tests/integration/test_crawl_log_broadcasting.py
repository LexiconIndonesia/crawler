"""Integration tests for crawl log broadcasting during job execution."""

import asyncio
import json
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from config import get_settings
from crawler.api.generated import CrawlStep, MethodEnum, StepConfig, StepTypeEnum
from crawler.api.websocket_models import WebSocketLogMessage
from crawler.db.generated.models import CrawlLog, LogLevelEnum
from crawler.db.repositories import CrawlJobRepository, CrawlLogRepository, WebsiteRepository
from crawler.services import SeedURLCrawler, SeedURLCrawlerConfig
from crawler.services.log_publisher import LogPublisher
from crawler.services.nats_queue import NATSQueueService


async def poll_for_condition(
    condition: Callable[[], bool],
    fetch_data: Callable[[], Any],
    timeout: float = 2.0,
    poll_interval: float = 0.1,
    error_message: str = "Condition not met within timeout",
) -> Any:
    """Poll for a condition to be met with timeout.

    Args:
        condition: Callable that checks if the expected condition is met
        fetch_data: Callable that fetches the latest data
        timeout: Maximum time to wait in seconds
        poll_interval: Time between polls in seconds
        error_message: Error message to raise if timeout is reached

    Returns:
        The last fetched data when condition is met

    Raises:
        AssertionError: If condition is not met within timeout
    """
    max_iterations = int(timeout / poll_interval)
    data = None

    for _ in range(max_iterations):
        data = await fetch_data()
        if condition():
            return data
        await asyncio.sleep(poll_interval)

    pytest.fail(error_message)


@pytest.mark.asyncio
class TestCrawlLogBroadcasting:
    """Test crawl log broadcasting during actual crawl execution."""

    async def test_crawler_writes_logs_during_execution(
        self,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that crawler writes logs to database during crawl execution."""
        settings = get_settings()

        # Create website and job
        website_repo = WebsiteRepository(db_connection)
        website = await website_repo.create(
            name="Test Website - Crawler Logs",
            base_url="https://example.com",
            config={},
        )

        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create(
            website_id=website.id,
            seed_url="https://example.com/products",
        )

        # Setup NATS
        nats_service = NATSQueueService(settings)
        await nats_service.connect()

        try:
            # Create log publisher
            log_publisher = LogPublisher(nats_client=nats_service.client)
            log_repo = CrawlLogRepository(db_connection, log_publisher=log_publisher)

            # Mock HTTP client that returns fake HTML
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"""
                <html>
                    <body>
                        <a href="/product/1">Product 1</a>
                        <a href="/product/2">Product 2</a>
                    </body>
                </html>
            """

            mock_http_client = AsyncMock(spec=httpx.AsyncClient)
            mock_http_client.get = AsyncMock(return_value=mock_response)

            # Create crawler config with log repository
            crawl_step = CrawlStep(
                name="test_step",
                type=StepTypeEnum.crawl,
                description="Test crawl step",
                method=MethodEnum.http,
                config=StepConfig(
                    url="https://example.com/products",
                    detail_url_selector="a",
                    pagination={"enabled": False},
                ),
                selectors={"detail_urls": "a"},
                output=None,
            )

            crawler_config = SeedURLCrawlerConfig(
                step=crawl_step,
                job_id=str(job.id),
                website_id=str(website.id),
                http_client=mock_http_client,
                crawl_log_repo=log_repo,
            )

            # Execute crawl (should write logs in background)
            crawler = SeedURLCrawler()
            await crawler.crawl("https://example.com/products", crawler_config)

            # Wait briefly for background log tasks to start, then poll for completion
            await asyncio.sleep(0.2)  # Give tasks time to spawn

            logs: list[CrawlLog] = []

            async def fetch_logs() -> list[CrawlLog]:
                nonlocal logs
                logs = await log_repo.list_by_job(job_id=job.id, limit=100)
                return logs

            await poll_for_condition(
                condition=lambda: len(logs) > 0,
                fetch_data=fetch_logs,
                timeout=1.5,
                poll_interval=0.1,
                error_message="No logs found in database after waiting",
            )

            # Should have multiple logs from the crawl
            assert len(logs) > 0, "No logs were written during crawl"

            # Verify log content
            log_messages = [log.message for log in logs]
            log_steps = [log.step_name for log in logs]

            # Check for expected log messages
            assert any("Starting crawl" in msg for msg in log_messages), "Missing crawl start log"
            assert any("Fetched seed URL" in msg for msg in log_messages), (
                "Missing seed URL fetch log"
            )
            assert any("Crawl completed" in msg for msg in log_messages), (
                "Missing crawl completion log"
            )

            # Check for expected log steps
            assert "crawl_start" in log_steps
            assert "fetch_seed_url" in log_steps
            assert "crawl_complete" in log_steps

            # Verify at least one log has INFO level
            assert any(log.log_level == LogLevelEnum.INFO for log in logs)

        finally:
            await nats_service.disconnect()

    async def test_crawler_logs_are_broadcast_to_nats(
        self,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that crawler logs are broadcast to NATS in real-time."""
        settings = get_settings()

        # Create website and job
        website_repo = WebsiteRepository(db_connection)
        website = await website_repo.create(
            name="Test Website - NATS Broadcast",
            base_url="https://example.com",
            config={},
        )

        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create(
            website_id=website.id,
            seed_url="https://example.com/products",
        )

        # Setup NATS
        nats_service = NATSQueueService(settings)
        await nats_service.connect()

        try:
            # Subscribe to NATS subject for this job
            subject = f"logs.{job.id}"
            subscription = await nats_service.client.subscribe(subject)

            # Create log publisher
            log_publisher = LogPublisher(nats_client=nats_service.client)
            log_repo = CrawlLogRepository(db_connection, log_publisher=log_publisher)

            # Mock HTTP client
            mock_response = Mock()
            mock_response.status_code = 200
            mock_response.content = b"<html><a href='/product/1'>Product 1</a></html>"

            mock_http_client = AsyncMock(spec=httpx.AsyncClient)
            mock_http_client.get = AsyncMock(return_value=mock_response)

            # Create crawler config
            crawl_step = CrawlStep(
                name="test_step",
                type=StepTypeEnum.crawl,
                description="Test crawl step",
                method=MethodEnum.http,
                config=StepConfig(
                    url="https://example.com/products",
                    detail_url_selector="a",
                    pagination={"enabled": False},
                ),
                selectors={"detail_urls": "a"},
                output=None,
            )

            crawler_config = SeedURLCrawlerConfig(
                step=crawl_step,
                job_id=str(job.id),
                website_id=str(website.id),
                http_client=mock_http_client,
                crawl_log_repo=log_repo,
            )

            # Start listening for NATS messages in background
            received_messages = []

            async def collect_messages():
                """Collect NATS messages for 2 seconds."""
                try:
                    for _ in range(20):  # Try to receive up to 20 messages
                        msg = await asyncio.wait_for(subscription.next_msg(), timeout=0.5)
                        payload = json.loads(msg.data.decode("utf-8"))
                        ws_message = WebSocketLogMessage(**payload)
                        received_messages.append(ws_message)
                except TimeoutError:
                    pass  # No more messages

            # Start collector task
            collector_task = asyncio.create_task(collect_messages())

            # Execute crawl
            crawler = SeedURLCrawler()
            await crawler.crawl("https://example.com/products", crawler_config)

            # Wait for collector to finish
            await asyncio.wait_for(collector_task, timeout=3.0)

            # Verify messages were received
            assert len(received_messages) > 0, "No messages received from NATS"

            # Verify message format
            for ws_msg in received_messages:
                assert ws_msg.job_id == str(job.id)
                assert ws_msg.website_id == str(website.id)
                assert ws_msg.message is not None
                assert ws_msg.log_level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

            # Check for expected log types
            messages_text = [msg.message for msg in received_messages]
            assert any("Starting crawl" in msg for msg in messages_text)

            # Cleanup
            await subscription.unsubscribe()

        finally:
            await nats_service.disconnect()

    async def test_crawler_logs_on_error(
        self,
        db_connection: AsyncConnection,
    ) -> None:
        """Test that crawler writes error logs when crawl fails."""
        settings = get_settings()

        # Create website and job
        website_repo = WebsiteRepository(db_connection)
        website = await website_repo.create(
            name="Test Website - Error Logs",
            base_url="https://example.com",
            config={},
        )

        job_repo = CrawlJobRepository(db_connection)
        job = await job_repo.create(
            website_id=website.id,
            seed_url="https://example.com/404",
        )

        # Setup NATS
        nats_service = NATSQueueService(settings)
        await nats_service.connect()

        try:
            # Create log publisher
            log_publisher = LogPublisher(nats_client=nats_service.client)
            log_repo = CrawlLogRepository(db_connection, log_publisher=log_publisher)

            # Mock HTTP client that returns 404
            mock_response = Mock()
            mock_response.status_code = 404
            mock_response.content = b"Not Found"

            mock_http_client = AsyncMock(spec=httpx.AsyncClient)
            mock_http_client.get = AsyncMock(return_value=mock_response)

            # Create crawler config
            crawl_step = CrawlStep(
                name="test_step",
                type=StepTypeEnum.crawl,
                description="Test crawl step",
                method=MethodEnum.http,
                config=StepConfig(
                    url="https://example.com/404",
                    detail_url_selector="a",
                    pagination={"enabled": False},
                ),
                selectors={"detail_urls": "a"},
                output=None,
            )

            crawler_config = SeedURLCrawlerConfig(
                step=crawl_step,
                job_id=str(job.id),
                website_id=str(website.id),
                http_client=mock_http_client,
                crawl_log_repo=log_repo,
            )

            # Execute crawl (should fail with 404)
            crawler = SeedURLCrawler()
            await crawler.crawl("https://example.com/404", crawler_config)

            # Wait briefly for background log tasks to start, then poll for completion
            await asyncio.sleep(0.2)  # Give tasks time to spawn

            logs: list[CrawlLog] = []

            async def fetch_logs() -> list[CrawlLog]:
                nonlocal logs
                logs = await log_repo.list_by_job(job_id=job.id, limit=100)
                return logs

            await poll_for_condition(
                condition=lambda: len(logs) > 0,
                fetch_data=fetch_logs,
                timeout=1.5,
                poll_interval=0.1,
                error_message="No logs found in database after waiting",
            )

            # Verify logs were written
            assert len(logs) > 0, "No logs written for failed crawl"

            # Verify error log exists
            error_logs = [log for log in logs if log.log_level == LogLevelEnum.ERROR]
            assert len(error_logs) > 0, "No error logs found for 404"

            # Verify error message content
            error_messages = [log.message for log in error_logs]
            assert any("404" in msg for msg in error_messages), "Error log doesn't mention 404"

        finally:
            await nats_service.disconnect()
