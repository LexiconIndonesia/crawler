"""Integration tests for job logs API endpoint."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import models
from crawler.db.generated.models import JobTypeEnum, LogLevelEnum
from crawler.db.repositories import CrawlJobRepository, CrawlLogRepository, WebsiteRepository


@pytest.fixture
async def test_job(
    db_connection: AsyncConnection,
) -> AsyncGenerator[tuple[models.CrawlJob, models.Website], None]:
    """Create a test website and crawl job for log tests.

    Returns:
        Tuple of (job, website) that can be used in tests
    """
    # Create test website
    website_repo = WebsiteRepository(db_connection)
    unique_id = str(uuid.uuid4())[:8]
    website = await website_repo.create(
        name=f"Test Website {unique_id}",
        base_url=f"https://example-{unique_id}.com",
        config={},
    )
    assert website is not None

    # Create test job
    crawl_job_repo = CrawlJobRepository(db_connection)
    job = await crawl_job_repo.create(
        seed_url="https://example.com",
        website_id=website.id,
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
    )
    assert job is not None

    # Commit so test_client can see the data
    await db_connection.commit()

    yield job, website


@pytest.mark.asyncio
async def test_get_job_logs_success(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_job: tuple[models.CrawlJob, models.Website],
) -> None:
    """Test successful retrieval of job logs."""
    job, website = test_job

    # Create test logs
    crawl_log_repo = CrawlLogRepository(db_connection)
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Test log message 1",
        log_level=LogLevelEnum.INFO,
        step_name="test_step",
    )
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Test log message 2",
        log_level=LogLevelEnum.WARNING,
        step_name="test_step",
    )
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Error occurred",
        log_level=LogLevelEnum.ERROR,
        step_name="test_step",
    )

    # Commit transaction so test_client can see the data
    await db_connection.commit()

    # Test getting all logs
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs")
    assert response.status_code == 200

    data = response.json()
    assert "logs" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    assert data["total"] == 3
    assert len(data["logs"]) == 3
    assert data["limit"] == 100
    assert data["offset"] == 0

    # Verify log structure
    log = data["logs"][0]
    assert "id" in log
    assert "job_id" in log
    assert "website_id" in log
    assert "log_level" in log
    assert "message" in log
    assert "created_at" in log


@pytest.mark.asyncio
async def test_get_job_logs_with_log_level_filter(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_job: tuple[models.CrawlJob, models.Website],
) -> None:
    """Test filtering logs by log level."""
    job, website = test_job

    # Create test logs with different levels
    crawl_log_repo = CrawlLogRepository(db_connection)
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Info message",
        log_level=LogLevelEnum.INFO,
    )
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Error message",
        log_level=LogLevelEnum.ERROR,
    )

    # Commit transaction so test_client can see the data
    await db_connection.commit()

    # Filter by ERROR level
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?log_level=ERROR")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert len(data["logs"]) == 1
    assert data["logs"][0]["log_level"] == "ERROR"
    assert data["logs"][0]["message"] == "Error message"


@pytest.mark.asyncio
async def test_get_job_logs_with_search(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_job: tuple[models.CrawlJob, models.Website],
) -> None:
    """Test searching logs by text."""
    job, website = test_job

    # Create test logs
    crawl_log_repo = CrawlLogRepository(db_connection)
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Successfully fetched page",
        log_level=LogLevelEnum.INFO,
    )
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Error connecting to server",
        log_level=LogLevelEnum.ERROR,
    )

    # Commit transaction so test_client can see the data
    await db_connection.commit()

    # Search for "error"
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?search=error")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 1
    assert len(data["logs"]) == 1
    assert "error" in data["logs"][0]["message"].lower()


@pytest.mark.asyncio
async def test_get_job_logs_with_pagination(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_job: tuple[models.CrawlJob, models.Website],
) -> None:
    """Test pagination of logs."""
    job, website = test_job

    # Create 10 test logs
    crawl_log_repo = CrawlLogRepository(db_connection)
    for i in range(10):
        await crawl_log_repo.create(
            job_id=job.id,
            website_id=website.id,
            message=f"Log message {i}",
            log_level=LogLevelEnum.INFO,
        )

    # Commit transaction so test_client can see the data
    await db_connection.commit()

    # Get first page (5 logs)
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?limit=5&offset=0")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 10
    assert len(data["logs"]) == 5
    assert data["limit"] == 5
    assert data["offset"] == 0

    # Get second page (5 logs)
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?limit=5&offset=5")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 10
    assert len(data["logs"]) == 5
    assert data["limit"] == 5
    assert data["offset"] == 5


@pytest.mark.asyncio
async def test_get_job_logs_with_time_range(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_job: tuple[models.CrawlJob, models.Website],
) -> None:
    """Test filtering logs by time range."""
    job, website = test_job

    # Record timestamp well before creating logs
    before_logs = datetime.now(UTC) - timedelta(seconds=2)

    # Create logs (they will have auto-generated timestamps)
    crawl_log_repo = CrawlLogRepository(db_connection)
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="First log",
        log_level=LogLevelEnum.INFO,
    )
    await crawl_log_repo.create(
        job_id=job.id,
        website_id=website.id,
        message="Second log",
        log_level=LogLevelEnum.INFO,
    )

    # Record timestamp well after creating logs
    after_logs = datetime.now(UTC) + timedelta(seconds=2)

    # Commit transaction so test_client can see the data
    await db_connection.commit()

    # Test 1: Query with start_time before logs - should get all logs
    start_time_before = before_logs.isoformat().replace("+00:00", "Z")
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?start_time={start_time_before}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2, "Should get all logs when start_time is before creation"

    # Test 2: Query with end_time before logs - should get no logs
    end_time_before = (before_logs - timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?end_time={end_time_before}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0, "Should get no logs when end_time is before creation"

    # Test 3: Query with start_time and end_time spanning logs - should get all logs
    start_time = before_logs.isoformat().replace("+00:00", "Z")
    end_time = after_logs.isoformat().replace("+00:00", "Z")
    response = await test_client.get(
        f"/api/v1/jobs/{job.id}/logs?start_time={start_time}&end_time={end_time}"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2, "Should get all logs within time range"

    # Test 4: Query with start_time after logs - should get no logs
    start_time_after = after_logs.isoformat().replace("+00:00", "Z")
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?start_time={start_time_after}")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 0, "Should get no logs when start_time is after creation"


@pytest.mark.asyncio
async def test_get_job_logs_job_not_found(
    test_client: AsyncClient,
) -> None:
    """Test retrieving logs for non-existent job."""
    fake_job_id = "550e8400-e29b-41d4-a716-446655440000"
    response = await test_client.get(f"/api/v1/jobs/{fake_job_id}/logs")
    assert response.status_code == 404

    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


@pytest.mark.asyncio
async def test_get_job_logs_empty_result(
    test_client: AsyncClient,
    test_job: tuple[models.CrawlJob, models.Website],
) -> None:
    """Test retrieving logs when there are no logs."""
    job, _website = test_job

    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] == 0
    assert len(data["logs"]) == 0
    assert data["limit"] == 100
    assert data["offset"] == 0


@pytest.mark.asyncio
async def test_get_job_logs_invalid_limit(
    test_client: AsyncClient,
    test_job: tuple[models.CrawlJob, models.Website],
) -> None:
    """Test with invalid limit parameter."""
    job, _website = test_job

    # Try with limit > 1000
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?limit=2000")
    assert response.status_code == 422  # Validation error

    # Try with limit < 1
    response = await test_client.get(f"/api/v1/jobs/{job.id}/logs?limit=0")
    assert response.status_code == 422  # Validation error
