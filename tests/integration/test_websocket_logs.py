"""Integration tests for WebSocket log streaming endpoint."""

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from crawler.db.generated import models
from crawler.db.generated.models import JobTypeEnum, LogLevelEnum
from crawler.db.repositories import CrawlJobRepository, CrawlLogRepository, WebsiteRepository
from main import create_app


@pytest.fixture
async def test_ws_job(
    db_connection: AsyncConnection,
) -> AsyncGenerator[tuple[models.CrawlJob, models.Website], None]:
    """Create a test website and crawl job for WebSocket tests.

    Returns:
        Tuple of (job, website) that can be used in tests
    """
    # Create test website
    website_repo = WebsiteRepository(db_connection)
    unique_id = str(uuid.uuid4())[:8]
    website = await website_repo.create(
        name=f"Test WS Website {unique_id}",
        base_url=f"https://ws-example-{unique_id}.com",
        config={},
    )
    assert website is not None

    # Create test job
    crawl_job_repo = CrawlJobRepository(db_connection)
    job = await crawl_job_repo.create(
        seed_url="https://ws-example.com",
        website_id=website.id,
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
    )
    assert job is not None

    # Commit so test_client can see the data
    await db_connection.commit()

    yield job, website


@pytest.mark.asyncio
class TestWebSocketLogStreaming:
    """Test suite for WebSocket log streaming functionality.

    Note: These are basic security tests. Full end-to-end tests with real log streaming
    require complex transaction management and are covered in manual/E2E testing.
    """

    async def test_token_generation_job_not_found(self, test_client: AsyncClient):
        """Test token generation fails for non-existent job (security test)."""
        fake_job_id = str(uuid.uuid4())
        response = await test_client.post(f"/api/v1/jobs/{fake_job_id}/ws-token")

        # Per OpenAPI spec, job not found should return 404, not 400
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    async def test_websocket_invalid_token_rejects_connection(self):
        """Test WebSocket connection fails with invalid token (security test)."""
        fake_job_id = str(uuid.uuid4())
        app = create_app()

        with TestClient(app) as client:
            with pytest.raises(WebSocketDisconnect) as exc_info:
                with client.websocket_connect(
                    f"/ws/v1/jobs/{fake_job_id}/logs?token=invalid_token"
                ):
                    pass

            # WS_1008_POLICY_VIOLATION - token rejected
            assert exc_info.value.code == 1008

    async def test_log_buffer_stores_and_retrieves_logs(
        self,
        db_connection: AsyncConnection,
        test_ws_job: tuple[models.CrawlJob, models.Website],
    ):
        """Test that LogBuffer correctly stores and retrieves logs for reconnection.

        Note: This is a unit test for the LogBuffer service used by WebSocket reconnection.
        Full E2E WebSocket tests require complex async/sync coordination and are
        better suited for manual testing.
        """
        import redis.asyncio as redis

        from config import get_settings
        from crawler.services.redis_cache import LogBuffer

        job, website = test_ws_job
        settings = get_settings()

        # Create Redis client and LogBuffer
        redis_client = await redis.from_url(settings.redis_url)
        log_buffer = LogBuffer(redis_client=redis_client, settings=settings)

        try:
            # Create test logs
            crawl_log_repo = CrawlLogRepository(db_connection)
            log1 = await crawl_log_repo.create(
                job_id=job.id,
                website_id=website.id,
                message="First log message",
                log_level=LogLevelEnum.INFO,
            )
            log2 = await crawl_log_repo.create(
                job_id=job.id,
                website_id=website.id,
                message="Second log message",
                log_level=LogLevelEnum.INFO,
            )
            log3 = await crawl_log_repo.create(
                job_id=job.id,
                website_id=website.id,
                message="Third log message",
                log_level=LogLevelEnum.INFO,
            )
            await db_connection.commit()

            assert log1 is not None
            assert log2 is not None
            assert log3 is not None

            # Add logs to buffer
            await log_buffer.add_log(
                job_id=str(job.id),
                log_id=log1.id,
                log_data={"id": log1.id, "message": log1.message},
            )
            await log_buffer.add_log(
                job_id=str(job.id),
                log_id=log2.id,
                log_data={"id": log2.id, "message": log2.message},
            )
            await log_buffer.add_log(
                job_id=str(job.id),
                log_id=log3.id,
                log_data={"id": log3.id, "message": log3.message},
            )

            # Test: Get logs after log1.id (should return log2 and log3)
            logs_after_1 = await log_buffer.get_logs_after_id(
                job_id=str(job.id), after_log_id=log1.id
            )
            assert len(logs_after_1) == 2
            assert logs_after_1[0]["id"] == log2.id
            assert logs_after_1[1]["id"] == log3.id

            # Test: Get logs after log2.id (should return only log3)
            logs_after_2 = await log_buffer.get_logs_after_id(
                job_id=str(job.id), after_log_id=log2.id
            )
            assert len(logs_after_2) == 1
            assert logs_after_2[0]["id"] == log3.id

            # Test: Get logs after log3.id (should return empty)
            logs_after_3 = await log_buffer.get_logs_after_id(
                job_id=str(job.id), after_log_id=log3.id
            )
            assert len(logs_after_3) == 0

            # Test: Check buffer size
            buffer_size = await log_buffer.get_buffer_size(job_id=str(job.id))
            assert buffer_size == 3

        finally:
            # Cleanup
            await log_buffer.clear_buffer(job_id=str(job.id))
            await redis_client.aclose()

    async def test_crawl_log_repository_get_logs_after_id(
        self,
        db_connection: AsyncConnection,
        test_ws_job: tuple[models.CrawlJob, models.Website],
    ):
        """Test CrawlLogRepository.get_logs_after_id for database-based reconnection fallback."""
        job, website = test_ws_job

        # Create test logs
        crawl_log_repo = CrawlLogRepository(db_connection)
        log1 = await crawl_log_repo.create(
            job_id=job.id,
            website_id=website.id,
            message="First log",
            log_level=LogLevelEnum.INFO,
        )
        log2 = await crawl_log_repo.create(
            job_id=job.id,
            website_id=website.id,
            message="Second log",
            log_level=LogLevelEnum.INFO,
        )
        log3 = await crawl_log_repo.create(
            job_id=job.id,
            website_id=website.id,
            message="Third log",
            log_level=LogLevelEnum.INFO,
        )
        await db_connection.commit()

        assert log1 is not None
        assert log2 is not None
        assert log3 is not None

        # Test: Get logs after log1.id
        logs_after_1 = await crawl_log_repo.get_logs_after_id(job_id=job.id, after_log_id=log1.id)
        assert len(logs_after_1) == 2
        assert logs_after_1[0].id == log2.id
        assert logs_after_1[1].id == log3.id

        # Test: Get logs after log2.id
        logs_after_2 = await crawl_log_repo.get_logs_after_id(job_id=job.id, after_log_id=log2.id)
        assert len(logs_after_2) == 1
        assert logs_after_2[0].id == log3.id

        # Test: Get logs after log3.id (should be empty)
        logs_after_3 = await crawl_log_repo.get_logs_after_id(job_id=job.id, after_log_id=log3.id)
        assert len(logs_after_3) == 0
