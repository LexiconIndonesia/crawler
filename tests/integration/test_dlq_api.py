"""Integration tests for DLQ API endpoints."""

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import models
from crawler.db.generated.models import ErrorCategoryEnum, JobTypeEnum
from crawler.db.repositories import CrawlJobRepository, DeadLetterQueueRepository, WebsiteRepository


@pytest.fixture
async def test_dlq_entry(
    db_connection: AsyncConnection,
) -> AsyncGenerator[tuple[models.DeadLetterQueue, models.CrawlJob], None]:
    """Create a test DLQ entry for API tests.

    Returns:
        Tuple of (dlq_entry, job) that can be used in tests
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
        seed_url="https://example.com/page",
        website_id=website.id,
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
    )
    assert job is not None

    # Create DLQ entry
    dlq_repo = DeadLetterQueueRepository(db_connection)
    dlq_entry = await dlq_repo.add_to_dlq(
        job_id=str(job.id),
        seed_url="https://example.com/page",
        website_id=str(website.id),
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
        error_category=ErrorCategoryEnum.NOT_FOUND,
        error_message="Page not found",
        stack_trace="Traceback...",
        http_status=404,
        total_attempts=3,
        first_attempt_at=datetime.now(UTC),
        last_attempt_at=datetime.now(UTC),
    )

    # Commit so test_client can see the data
    await db_connection.commit()

    yield dlq_entry, job


# ============================================================================
# List DLQ Entries Tests
# ============================================================================


@pytest.mark.asyncio
async def test_list_dlq_entries_success(
    test_client: AsyncClient,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test successful retrieval of DLQ entries."""
    dlq_entry, _job = test_dlq_entry

    response = await test_client.get("/api/v1/dlq/entries")
    assert response.status_code == 200

    data = response.json()
    assert "entries" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data

    assert data["total"] >= 1
    assert len(data["entries"]) >= 1
    assert data["limit"] == 100
    assert data["offset"] == 0

    # Verify entry structure
    entry = next((e for e in data["entries"] if e["id"] == dlq_entry.id), None)
    assert entry is not None
    assert "id" in entry
    assert "job_id" in entry
    assert "seed_url" in entry
    assert "error_category" in entry
    assert "error_message" in entry
    assert "total_attempts" in entry


@pytest.mark.asyncio
async def test_list_dlq_entries_with_error_category_filter(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
) -> None:
    """Test filtering DLQ entries by error category."""
    # Create DLQ entries with different error categories
    dlq_repo = DeadLetterQueueRepository(db_connection)
    website_repo = WebsiteRepository(db_connection)
    crawl_job_repo = CrawlJobRepository(db_connection)

    # Create website and job
    unique_id = str(uuid.uuid4())[:8]
    website = await website_repo.create(
        name=f"Test Website {unique_id}",
        base_url=f"https://example-{unique_id}.com",
        config={},
    )
    job = await crawl_job_repo.create(
        seed_url="https://example.com/timeout",
        website_id=website.id,
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
    )

    # Create TIMEOUT entry
    await dlq_repo.add_to_dlq(
        job_id=str(job.id),
        seed_url="https://example.com/timeout",
        website_id=str(website.id),
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
        error_category=ErrorCategoryEnum.TIMEOUT,
        error_message="Connection timeout",
        stack_trace=None,
        http_status=None,
        total_attempts=2,
        first_attempt_at=datetime.now(UTC),
        last_attempt_at=datetime.now(UTC),
    )

    await db_connection.commit()

    # Filter by TIMEOUT category
    response = await test_client.get("/api/v1/dlq/entries?error_category=timeout")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 1
    # All returned entries should be TIMEOUT
    for entry in data["entries"]:
        assert entry["error_category"] == "timeout"


@pytest.mark.asyncio
async def test_list_dlq_entries_with_unresolved_filter(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test filtering DLQ entries by resolved status."""
    dlq_entry, _job = test_dlq_entry

    # Mark the entry as resolved
    dlq_repo = DeadLetterQueueRepository(db_connection)
    await dlq_repo.mark_resolved(dlq_entry.id, "Fixed manually")
    await db_connection.commit()

    # Filter for unresolved only - should not include our resolved entry
    response = await test_client.get("/api/v1/dlq/entries?unresolved_only=true")
    assert response.status_code == 200

    data = response.json()
    # Our resolved entry should not be in the results
    entry_ids = [e["id"] for e in data["entries"]]
    assert dlq_entry.id not in entry_ids

    # Filter for resolved only - should include our entry
    response = await test_client.get("/api/v1/dlq/entries?unresolved_only=false")
    assert response.status_code == 200

    data = response.json()
    entry_ids = [e["id"] for e in data["entries"]]
    assert dlq_entry.id in entry_ids


@pytest.mark.asyncio
async def test_list_dlq_entries_with_pagination(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
) -> None:
    """Test pagination of DLQ entries."""
    # Create 10 DLQ entries
    dlq_repo = DeadLetterQueueRepository(db_connection)
    website_repo = WebsiteRepository(db_connection)
    crawl_job_repo = CrawlJobRepository(db_connection)

    unique_id = str(uuid.uuid4())[:8]
    website = await website_repo.create(
        name=f"Test Website {unique_id}",
        base_url=f"https://example-{unique_id}.com",
        config={},
    )

    for i in range(10):
        job = await crawl_job_repo.create(
            seed_url=f"https://example.com/page{i}",
            website_id=website.id,
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
        )
        await dlq_repo.add_to_dlq(
            job_id=str(job.id),
            seed_url=f"https://example.com/page{i}",
            website_id=str(website.id),
            job_type=JobTypeEnum.ONE_TIME,
            priority=5,
            error_category=ErrorCategoryEnum.NOT_FOUND,
            error_message=f"Page {i} not found",
            stack_trace=None,
            http_status=404,
            total_attempts=3,
            first_attempt_at=datetime.now(UTC),
            last_attempt_at=datetime.now(UTC),
        )

    await db_connection.commit()

    # Get first page (5 entries)
    response = await test_client.get("/api/v1/dlq/entries?limit=5&offset=0")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 10
    assert len(data["entries"]) == 5
    assert data["limit"] == 5
    assert data["offset"] == 0

    # Get second page (5 entries)
    response = await test_client.get("/api/v1/dlq/entries?limit=5&offset=5")
    assert response.status_code == 200

    data = response.json()
    assert data["total"] >= 10
    assert len(data["entries"]) == 5
    assert data["limit"] == 5
    assert data["offset"] == 5


@pytest.mark.asyncio
async def test_list_dlq_entries_invalid_limit(
    test_client: AsyncClient,
) -> None:
    """Test with invalid limit parameter."""
    # Try with limit > 500
    response = await test_client.get("/api/v1/dlq/entries?limit=1000")
    assert response.status_code == 422  # Validation error

    # Try with limit < 1
    response = await test_client.get("/api/v1/dlq/entries?limit=0")
    assert response.status_code == 422  # Validation error


# ============================================================================
# Get DLQ Entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_dlq_entry_success(
    test_client: AsyncClient,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test successful retrieval of a DLQ entry."""
    dlq_entry, _job = test_dlq_entry

    response = await test_client.get(f"/api/v1/dlq/entries/{dlq_entry.id}")
    assert response.status_code == 200

    data = response.json()
    assert "entry" in data

    entry = data["entry"]
    assert entry["id"] == dlq_entry.id
    assert entry["seed_url"] == "https://example.com/page"
    assert entry["error_category"] == "not_found"
    assert entry["error_message"] == "Page not found"
    assert entry["http_status"] == 404
    assert entry["total_attempts"] == 3


@pytest.mark.asyncio
async def test_get_dlq_entry_not_found(
    test_client: AsyncClient,
) -> None:
    """Test retrieving non-existent DLQ entry."""
    response = await test_client.get("/api/v1/dlq/entries/999999")
    assert response.status_code == 404

    data = response.json()
    assert "detail" in data
    assert "not found" in data["detail"].lower()


# ============================================================================
# Retry DLQ Entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_retry_dlq_entry_success(
    test_client: AsyncClient,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test successful retry of a DLQ entry."""
    dlq_entry, _job = test_dlq_entry

    response = await test_client.post(f"/api/v1/dlq/entries/{dlq_entry.id}/retry")
    assert response.status_code == 200

    data = response.json()
    assert "job_id" in data
    assert "dlq_entry_id" in data
    assert "message" in data

    assert data["dlq_entry_id"] == dlq_entry.id
    assert "successfully" in data["message"].lower()


@pytest.mark.asyncio
async def test_retry_dlq_entry_not_found(
    test_client: AsyncClient,
) -> None:
    """Test retrying non-existent DLQ entry."""
    response = await test_client.post("/api/v1/dlq/entries/999999/retry")
    assert response.status_code == 404

    data = response.json()
    assert "detail" in data


@pytest.mark.asyncio
async def test_retry_dlq_entry_already_resolved(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test retrying an already resolved DLQ entry."""
    dlq_entry, _job = test_dlq_entry

    # Mark as resolved first
    dlq_repo = DeadLetterQueueRepository(db_connection)
    await dlq_repo.mark_resolved(dlq_entry.id, "Already fixed")
    await db_connection.commit()

    # Try to retry
    response = await test_client.post(f"/api/v1/dlq/entries/{dlq_entry.id}/retry")
    assert response.status_code == 400  # ValueError -> 400

    data = response.json()
    assert "detail" in data
    assert "resolved" in data["detail"].lower()


# ============================================================================
# Resolve DLQ Entry Tests
# ============================================================================


@pytest.mark.asyncio
async def test_resolve_dlq_entry_success(
    test_client: AsyncClient,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test successful resolution of a DLQ entry."""
    dlq_entry, _job = test_dlq_entry

    payload = {"resolution_notes": "Fixed the configuration issue"}

    response = await test_client.post(f"/api/v1/dlq/entries/{dlq_entry.id}/resolve", json=payload)
    assert response.status_code == 200

    data = response.json()
    assert "entry" in data

    entry = data["entry"]
    assert entry["id"] == dlq_entry.id
    assert entry["resolved_at"] is not None
    assert entry["resolution_notes"] == "Fixed the configuration issue"


@pytest.mark.asyncio
async def test_resolve_dlq_entry_without_notes(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
) -> None:
    """Test resolving a DLQ entry without notes."""
    # Create a new DLQ entry
    dlq_repo = DeadLetterQueueRepository(db_connection)
    website_repo = WebsiteRepository(db_connection)
    crawl_job_repo = CrawlJobRepository(db_connection)

    unique_id = str(uuid.uuid4())[:8]
    website = await website_repo.create(
        name=f"Test Website {unique_id}",
        base_url=f"https://example-{unique_id}.com",
        config={},
    )
    job = await crawl_job_repo.create(
        seed_url="https://example.com/test",
        website_id=website.id,
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
    )
    dlq_entry = await dlq_repo.add_to_dlq(
        job_id=str(job.id),
        seed_url="https://example.com/test",
        website_id=str(website.id),
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
        error_category=ErrorCategoryEnum.NOT_FOUND,
        error_message="Test error",
        stack_trace=None,
        http_status=404,
        total_attempts=3,
        first_attempt_at=datetime.now(UTC),
        last_attempt_at=datetime.now(UTC),
    )
    await db_connection.commit()

    # Resolve without notes (send empty body or no body)
    response = await test_client.post(f"/api/v1/dlq/entries/{dlq_entry.id}/resolve")
    assert response.status_code == 200

    data = response.json()
    entry = data["entry"]
    assert entry["resolved_at"] is not None
    assert entry["resolution_notes"] is None


@pytest.mark.asyncio
async def test_resolve_dlq_entry_already_resolved(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test resolving an already resolved DLQ entry."""
    dlq_entry, _job = test_dlq_entry

    # Mark as resolved first
    dlq_repo = DeadLetterQueueRepository(db_connection)
    await dlq_repo.mark_resolved(dlq_entry.id, "Already fixed")
    await db_connection.commit()

    # Try to resolve again
    payload = {"resolution_notes": "Trying again"}
    response = await test_client.post(f"/api/v1/dlq/entries/{dlq_entry.id}/resolve", json=payload)
    assert response.status_code == 400  # ValueError -> 400

    data = response.json()
    assert "detail" in data
    assert "resolved" in data["detail"].lower()


@pytest.mark.asyncio
async def test_resolve_dlq_entry_not_found(
    test_client: AsyncClient,
) -> None:
    """Test resolving non-existent DLQ entry."""
    payload = {"resolution_notes": "Test notes"}
    response = await test_client.post("/api/v1/dlq/entries/999999/resolve", json=payload)
    assert response.status_code == 404

    data = response.json()
    assert "detail" in data


# ============================================================================
# Get DLQ Statistics Tests
# ============================================================================


@pytest.mark.asyncio
async def test_get_dlq_stats_success(
    test_client: AsyncClient,
    test_dlq_entry: tuple[models.DeadLetterQueue, models.CrawlJob],
) -> None:
    """Test successful retrieval of DLQ statistics."""
    _dlq_entry, _job = test_dlq_entry

    response = await test_client.get("/api/v1/dlq/stats")
    assert response.status_code == 200

    data = response.json()
    assert "total_entries" in data
    assert "unresolved_entries" in data
    assert "retry_attempts" in data
    assert "retry_successes" in data
    assert "by_category" in data

    assert data["total_entries"] >= 1
    assert data["unresolved_entries"] >= 1
    assert isinstance(data["by_category"], list)

    # Verify category stats structure
    if len(data["by_category"]) > 0:
        category_stat = data["by_category"][0]
        assert "error_category" in category_stat
        assert "total" in category_stat
        assert "unresolved" in category_stat


@pytest.mark.asyncio
async def test_get_dlq_stats_with_multiple_categories(
    test_client: AsyncClient,
    db_connection: AsyncConnection,
) -> None:
    """Test DLQ stats with multiple error categories."""
    # Create entries with different categories
    dlq_repo = DeadLetterQueueRepository(db_connection)
    website_repo = WebsiteRepository(db_connection)
    crawl_job_repo = CrawlJobRepository(db_connection)

    unique_id = str(uuid.uuid4())[:8]
    website = await website_repo.create(
        name=f"Test Website {unique_id}",
        base_url=f"https://example-{unique_id}.com",
        config={},
    )

    # NOT_FOUND entry
    job1 = await crawl_job_repo.create(
        seed_url="https://example.com/notfound",
        website_id=website.id,
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
    )
    await dlq_repo.add_to_dlq(
        job_id=str(job1.id),
        seed_url="https://example.com/notfound",
        website_id=str(website.id),
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
        error_category=ErrorCategoryEnum.NOT_FOUND,
        error_message="Not found",
        stack_trace=None,
        http_status=404,
        total_attempts=3,
        first_attempt_at=datetime.now(UTC),
        last_attempt_at=datetime.now(UTC),
    )

    # TIMEOUT entry
    job2 = await crawl_job_repo.create(
        seed_url="https://example.com/timeout",
        website_id=website.id,
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
    )
    await dlq_repo.add_to_dlq(
        job_id=str(job2.id),
        seed_url="https://example.com/timeout",
        website_id=str(website.id),
        job_type=JobTypeEnum.ONE_TIME,
        priority=5,
        error_category=ErrorCategoryEnum.TIMEOUT,
        error_message="Timeout",
        stack_trace=None,
        http_status=None,
        total_attempts=2,
        first_attempt_at=datetime.now(UTC),
        last_attempt_at=datetime.now(UTC),
    )

    await db_connection.commit()

    response = await test_client.get("/api/v1/dlq/stats")
    assert response.status_code == 200

    data = response.json()
    assert len(data["by_category"]) >= 2

    # Should have stats for both NOT_FOUND and TIMEOUT
    categories = [stat["error_category"] for stat in data["by_category"]]
    assert "not_found" in categories
    assert "timeout" in categories
