"""Integration tests for API routes.

These tests require running PostgreSQL and Redis instances.
Run with: make test-integration
"""

from datetime import UTC, datetime

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
class TestRootEndpoint:
    """Tests for root endpoint."""

    async def test_root_endpoint(self, test_client: AsyncClient) -> None:
        """Test root endpoint returns app info."""
        response = await test_client.get("/")
        assert response.status_code == 200

        data = response.json()
        assert "message" in data
        assert "version" in data
        assert "environment" in data
        assert "Lexicon Crawler" in data["message"]


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Tests for health check endpoint."""

    async def test_health_endpoint_success(self, test_client: AsyncClient) -> None:
        """Test health endpoint returns healthy status when services are up."""
        response = await test_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert "status" in data
        assert "timestamp" in data
        assert "checks" in data

        # Both database and Redis should be connected in test environment
        assert data["status"] == "healthy"
        assert data["checks"]["database"] == "connected"
        assert data["checks"]["redis"] == "connected"

    async def test_health_endpoint_structure(self, test_client: AsyncClient) -> None:
        """Test health endpoint returns correct structure."""
        response = await test_client.get("/health")
        assert response.status_code == 200

        data = response.json()
        # Verify response structure
        assert isinstance(data["status"], str)
        assert isinstance(data["timestamp"], str)
        assert isinstance(data["checks"], dict)
        assert "database" in data["checks"]
        assert "redis" in data["checks"]


@pytest.mark.asyncio
class TestMetricsEndpoint:
    """Tests for Prometheus metrics endpoint."""

    async def test_metrics_endpoint(self, test_client: AsyncClient) -> None:
        """Test metrics endpoint returns Prometheus format."""
        response = await test_client.get("/metrics")
        assert response.status_code == 200

        # Prometheus metrics should be plain text
        content_type = response.headers.get("content-type", "")
        assert "text/plain" in content_type or "prometheus" in content_type

        # Response should contain some metrics
        content = response.text
        assert len(content) > 0
        # Should contain HELP and TYPE comments for Prometheus
        assert "# HELP" in content or "# TYPE" in content


@pytest.mark.asyncio
class TestCreateWebsiteEndpoint:
    """Tests for POST /api/v1/websites endpoint."""

    async def test_create_website_minimal(self, test_client: AsyncClient) -> None:
        """Test creating a website with minimal configuration."""
        payload = {
            "name": "Test Website",
            "base_url": "https://example.com",
            "steps": [{"name": "crawl_list", "type": "crawl", "method": "api"}],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Website"
        assert (
            data["base_url"] == "https://example.com/"
        )  # AnyUrl normalizes URLs with trailing slash
        assert data["status"] == "active"
        assert "id" in data
        assert "cron_schedule" in data
        assert "next_run_time" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_website_with_schedule(self, test_client: AsyncClient) -> None:
        """Test creating a website with custom schedule."""
        payload = {
            "name": "Scheduled Website",
            "base_url": "https://example.com",
            "description": "Test website with custom schedule",
            "schedule": {
                "type": "recurring",
                "cron": "0 2 * * 1",  # Every Monday at 2 AM
                "timezone": "Asia/Jakarta",
                "enabled": True,
            },
            "steps": [{"name": "fetch_data", "type": "crawl", "method": "api"}],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Scheduled Website"
        assert data["cron_schedule"] == "0 2 * * 1"
        assert data["next_run_time"] is not None
        assert data["scheduled_job_id"] is not None

        # Verify next_run_time is in the future
        next_run = datetime.fromisoformat(data["next_run_time"].replace("Z", "+00:00"))
        assert next_run > datetime.now(UTC)

    async def test_create_website_with_multiple_steps(self, test_client: AsyncClient) -> None:
        """Test creating a website with multiple crawl steps."""
        payload = {
            "name": "Multi-Step Website",
            "base_url": "https://example.com",
            "steps": [
                {
                    "name": "crawl_list",
                    "type": "crawl",
                    "method": "api",
                    "description": "Get list of items",
                    "config": {"url": "https://api.example.com/items"},
                },
                {
                    "name": "scrape_detail",
                    "type": "scrape",
                    "method": "browser",
                    "browser_type": "playwright",
                    "description": "Extract content from detail pages",
                    "selectors": {
                        "title": "h1.title",
                        "content": "div.content",
                    },
                },
            ],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Multi-Step Website"
        assert len(data["config"]["steps"]) == 2
        assert data["config"]["steps"][0]["name"] == "crawl_list"
        assert data["config"]["steps"][1]["name"] == "scrape_detail"

    async def test_create_website_with_variables(self, test_client: AsyncClient) -> None:
        """Test creating a website with variables."""
        payload = {
            "name": "Website With Variables",
            "base_url": "https://example.com",
            "steps": [{"name": "fetch_data", "type": "crawl", "method": "api"}],
            "variables": {
                "api_key": "test_key",
                "page_size": 100,
            },
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["config"]["variables"]["api_key"] == "test_key"
        assert data["config"]["variables"]["page_size"] == 100

    async def test_create_website_duplicate_name(self, test_client: AsyncClient) -> None:
        """Test creating a website with duplicate name returns error."""
        payload = {
            "name": "Duplicate Test",
            "base_url": "https://example.com",
            "steps": [{"name": "test", "type": "crawl", "method": "api"}],
        }

        # Create first website
        response1 = await test_client.post("/api/v1/websites", json=payload)
        assert response1.status_code == 201

        # Try to create second website with same name
        response2 = await test_client.post("/api/v1/websites", json=payload)
        assert response2.status_code == 400

        error = response2.json()
        assert "already exists" in error["detail"]

    async def test_create_website_invalid_cron(self, test_client: AsyncClient) -> None:
        """Test creating a website with invalid cron expression."""
        payload = {
            "name": "Invalid Cron",
            "base_url": "https://example.com",
            "schedule": {
                "cron": "invalid cron",
            },
            "steps": [{"name": "test", "type": "crawl", "method": "api"}],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        # Pydantic validation returns 422 for invalid format
        assert response.status_code == 422

        error = response.json()
        # Pydantic returns validation errors in a different format
        assert "detail" in error

    async def test_create_website_invalid_url(self, test_client: AsyncClient) -> None:
        """Test creating a website with invalid base_url."""
        payload = {
            "name": "Invalid URL",
            "base_url": "not-a-valid-url",
            "steps": [{"name": "test", "type": "crawl", "method": "api"}],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 422  # Validation error

    async def test_create_website_no_steps(self, test_client: AsyncClient) -> None:
        """Test creating a website without steps."""
        payload = {
            "name": "No Steps",
            "base_url": "https://example.com",
            "steps": [],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 422  # Validation error

    async def test_create_website_duplicate_step_names(self, test_client: AsyncClient) -> None:
        """Test creating a website with duplicate step names."""
        payload = {
            "name": "Duplicate Steps",
            "base_url": "https://example.com",
            "steps": [
                {"name": "duplicate", "type": "crawl", "method": "api"},
                {"name": "duplicate", "type": "scrape", "method": "http"},
            ],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 422  # Validation error

        error = response.json()
        assert "Step names must be unique" in str(error)

    async def test_create_website_browser_without_browser_type(
        self, test_client: AsyncClient
    ) -> None:
        """Test creating a website with browser method but no browser_type."""
        payload = {
            "name": "Missing Browser Type",
            "base_url": "https://example.com",
            "steps": [
                {
                    "name": "scrape",
                    "type": "scrape",
                    "method": "browser",
                    # Missing browser_type
                }
            ],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 422  # Validation error

        error = response.json()
        assert "browser_type" in str(error).lower()

    async def test_create_website_with_global_config(self, test_client: AsyncClient) -> None:
        """Test creating a website with custom global configuration."""
        payload = {
            "name": "Custom Config Website",
            "base_url": "https://example.com",
            "steps": [{"name": "test", "type": "crawl", "method": "api"}],
            "global_config": {
                "rate_limit": {
                    "requests_per_second": 5.0,
                    "concurrent_pages": 10,
                },
                "timeout": {
                    "page_load": 60,
                    "http_request": 45,
                },
                "retry": {
                    "max_attempts": 5,
                    "backoff_strategy": "linear",
                },
            },
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["config"]["global_config"]["rate_limit"]["requests_per_second"] == 5.0
        assert data["config"]["global_config"]["timeout"]["page_load"] == 60
        assert data["config"]["global_config"]["retry"]["max_attempts"] == 5

    async def test_create_website_schedule_disabled(self, test_client: AsyncClient) -> None:
        """Test creating a website with schedule disabled."""
        payload = {
            "name": "Disabled Schedule",
            "base_url": "https://example.com",
            "schedule": {
                "enabled": False,
                "cron": "0 0 * * *",
            },
            "steps": [{"name": "test", "type": "crawl", "method": "api"}],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["next_run_time"] is None
        assert data["scheduled_job_id"] is None


@pytest.mark.asyncio
class TestGetWebsiteEndpoints:
    """Tests for GET /api/v1/websites endpoints."""

    async def test_list_websites_structure(self, test_client: AsyncClient) -> None:
        """Test listing websites response structure."""
        response = await test_client.get("/api/v1/websites")
        assert response.status_code == 200

        data = response.json()
        assert "websites" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data
        assert data["limit"] == 20
        assert data["offset"] == 0
        assert isinstance(data["websites"], list)
        assert isinstance(data["total"], int)
        assert len(data["websites"]) <= data["total"]

    async def test_list_websites(self, test_client: AsyncClient) -> None:
        """Test listing websites with multiple websites."""
        # Get initial count
        initial_response = await test_client.get("/api/v1/websites")
        initial_total = initial_response.json()["total"]

        # Create websites with unique names
        import time

        timestamp = int(time.time() * 1000)
        website1 = {
            "name": f"Test List Website 1 {timestamp}",
            "base_url": "https://list-example1.com",
            "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
        }
        website2 = {
            "name": f"Test List Website 2 {timestamp}",
            "base_url": "https://list-example2.com",
            "steps": [{"name": "crawl", "type": "crawl", "method": "http"}],
        }

        await test_client.post("/api/v1/websites", json=website1)
        await test_client.post("/api/v1/websites", json=website2)

        # List websites
        response = await test_client.get("/api/v1/websites")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == initial_total + 2
        # Check that our websites are in the list
        website_names = [w["name"] for w in data["websites"]]
        assert website1["name"] in website_names
        assert website2["name"] in website_names

    async def test_list_websites_with_pagination(self, test_client: AsyncClient) -> None:
        """Test listing websites with pagination."""
        # Get initial count
        initial_response = await test_client.get("/api/v1/websites")
        initial_total = initial_response.json()["total"]

        # Create 3 websites with unique names
        import time

        timestamp = int(time.time() * 1000)
        created_ids = []
        for i in range(3):
            resp = await test_client.post(
                "/api/v1/websites",
                json={
                    "name": f"Test Pagination Website {i} {timestamp}",
                    "base_url": f"https://pagination-example{i}-{timestamp}.com",
                    "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
                },
            )
            if resp.status_code == 201:
                created_ids.append(resp.json()["id"])

        # Get first page (limit 2)
        response = await test_client.get("/api/v1/websites?limit=2&offset=0")
        assert response.status_code == 200

        data = response.json()
        assert len(data["websites"]) == 2
        assert data["total"] == initial_total + len(created_ids)
        assert data["limit"] == 2
        assert data["offset"] == 0

        # Get second page
        response = await test_client.get(f"/api/v1/websites?limit=2&offset={initial_total}")
        assert response.status_code == 200

        data = response.json()
        assert data["total"] == initial_total + len(created_ids)
        assert data["offset"] == initial_total

    async def test_list_websites_filter_by_status(self, test_client: AsyncClient) -> None:
        """Test listing websites filtered by status."""
        # Create active and inactive websites
        await test_client.post(
            "/api/v1/websites",
            json={
                "name": "Active Website",
                "base_url": "https://active.com",
                "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
            },
        )

        # Filter by active status
        response = await test_client.get("/api/v1/websites?status=active")
        assert response.status_code == 200

        data = response.json()
        assert len(data["websites"]) >= 1
        assert all(w["status"] == "active" for w in data["websites"])

    async def test_get_website_by_id(self, test_client: AsyncClient) -> None:
        """Test retrieving a website by ID with statistics."""
        # Create website
        create_response = await test_client.post(
            "/api/v1/websites",
            json={
                "name": "Test Website for GET",
                "base_url": "https://example-get.com",
                "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
            },
        )
        assert create_response.status_code == 201

        website_id = create_response.json()["id"]

        # Get website by ID
        response = await test_client.get(f"/api/v1/websites/{website_id}")
        assert response.status_code == 200

        data = response.json()
        assert data["id"] == website_id
        assert data["name"] == "Test Website for GET"
        assert data["base_url"] == "https://example-get.com/"
        assert "statistics" in data
        assert data["statistics"]["total_jobs"] == 0  # No jobs run yet
        assert data["statistics"]["completed_jobs"] == 0
        assert data["statistics"]["success_rate"] == 0.0
        assert data["statistics"]["total_pages_crawled"] == 0
        assert data["statistics"]["last_crawl_at"] is None

    async def test_get_website_by_id_not_found(self, test_client: AsyncClient) -> None:
        """Test retrieving a non-existent website returns 404."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await test_client.get(f"/api/v1/websites/{fake_id}")
        assert response.status_code == 400  # ValueError -> 400 via decorator

        error = response.json()
        assert "not found" in error["detail"].lower()

    async def test_get_website_by_id_invalid_uuid(self, test_client: AsyncClient) -> None:
        """Test retrieving a website with invalid UUID format."""
        response = await test_client.get("/api/v1/websites/invalid-uuid")
        assert response.status_code in [400, 422]  # Validation error


@pytest.mark.asyncio
class TestUpdateWebsiteEndpoint:
    """Tests for PUT /api/v1/websites/{id} endpoint."""

    async def test_update_website_name(self, test_client: AsyncClient) -> None:
        """Test updating website name."""
        # Create website
        create_response = await test_client.post(
            "/api/v1/websites",
            json={
                "name": "Original Name",
                "base_url": "https://example.com",
                "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
            },
        )
        assert create_response.status_code == 201
        website_id = create_response.json()["id"]

        # Update website
        update_response = await test_client.put(
            f"/api/v1/websites/{website_id}",
            json={
                "name": "Updated Name",
                "change_reason": "Testing name update",
            },
        )
        assert update_response.status_code == 200

        data = update_response.json()
        assert data["name"] == "Updated Name"
        assert data["config_version"] == 1
        assert data["recrawl_job_id"] is None

    async def test_update_website_with_recrawl(self, test_client: AsyncClient) -> None:
        """Test updating website with re-crawl trigger."""
        # Create website
        create_response = await test_client.post(
            "/api/v1/websites",
            json={
                "name": "Test Site",
                "base_url": "https://example.com",
                "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
            },
        )
        website_id = create_response.json()["id"]

        # Update with recrawl
        update_response = await test_client.put(
            f"/api/v1/websites/{website_id}",
            json={
                "status": "active",
                "trigger_recrawl": True,
                "change_reason": "Testing recrawl",
            },
        )
        assert update_response.status_code == 200

        data = update_response.json()
        assert data["recrawl_job_id"] is not None
        assert data["config_version"] == 1

    async def test_update_website_not_found(self, test_client: AsyncClient) -> None:
        """Test updating non-existent website."""
        fake_id = "00000000-0000-0000-0000-000000000000"
        response = await test_client.put(
            f"/api/v1/websites/{fake_id}",
            json={"name": "New Name"},
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"].lower()

    async def test_update_website_no_changes(self, test_client: AsyncClient) -> None:
        """Test updating with no changes returns error."""
        # Create website
        create_response = await test_client.post(
            "/api/v1/websites",
            json={
                "name": "Test",
                "base_url": "https://example.com",
                "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
            },
        )
        website_id = create_response.json()["id"]

        # Update with no changes
        response = await test_client.put(
            f"/api/v1/websites/{website_id}",
            json={},
        )
        assert response.status_code == 400
        assert "no changes" in response.json()["detail"].lower()

    async def test_update_website_schedule(self, test_client: AsyncClient) -> None:
        """Test updating website schedule."""
        # Create website
        create_response = await test_client.post(
            "/api/v1/websites",
            json={
                "name": "Test Schedule",
                "base_url": "https://example.com",
                "steps": [{"name": "crawl", "type": "crawl", "method": "api"}],
            },
        )
        website_id = create_response.json()["id"]

        # Update schedule
        response = await test_client.put(
            f"/api/v1/websites/{website_id}",
            json={
                "schedule": {
                    "cron": "0 0 * * *",
                    "enabled": True,
                },
                "change_reason": "Change to daily schedule",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["cron_schedule"] == "0 0 * * *"
        assert data["next_run_time"] is not None


@pytest.mark.asyncio
class TestCreateSeedJobInlineEndpoint:
    """Tests for POST /api/v1/jobs/seed-inline endpoint."""

    async def test_create_seed_job_inline_minimal(self, test_client: AsyncClient) -> None:
        """Test creating an inline config seed job with minimal configuration."""
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [
                {
                    "name": "scrape_article",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {
                        "title": "h1.title",
                        "content": ".article-body",
                    },
                }
            ],
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["seed_url"] == "https://example.com/articles"
        assert data["website_id"] is None  # Inline jobs have no website_id
        assert data["status"] == "pending"
        assert data["job_type"] == "one_time"
        assert data["priority"] == 5  # Default priority
        assert data["scheduled_at"] is None
        assert "id" in data
        assert "created_at" in data
        assert "updated_at" in data

    async def test_create_seed_job_inline_with_custom_priority(
        self, test_client: AsyncClient
    ) -> None:
        """Test creating an inline config seed job with custom priority."""
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [
                {
                    "name": "scrape_article",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {"title": "h1.title"},
                }
            ],
            "priority": 9,
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["priority"] == 9

    async def test_create_seed_job_inline_with_variables(self, test_client: AsyncClient) -> None:
        """Test creating an inline config seed job with variables."""
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [
                {
                    "name": "scrape_article",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {"title": "h1.title"},
                }
            ],
            "variables": {
                "api_key": "test_key_123",
                "category": "technology",
            },
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["variables"]["api_key"] == "test_key_123"
        assert data["variables"]["category"] == "technology"

    async def test_create_seed_job_inline_with_global_config(
        self, test_client: AsyncClient
    ) -> None:
        """Test creating an inline config seed job with custom global configuration."""
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [
                {
                    "name": "scrape_article",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {"title": "h1.title"},
                }
            ],
            "global_config": {
                "rate_limit": {
                    "requests_per_second": 3.0,
                    "concurrent_pages": 8,
                },
                "timeout": {
                    "http_request": 45,
                },
            },
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["status"] == "pending"
        assert data["website_id"] is None

    async def test_create_seed_job_inline_with_custom_retry_config(
        self, test_client: AsyncClient, crawl_job_repo
    ) -> None:
        """Test creating an inline config seed job with custom retry configuration.

        Verifies that max_retries is sourced from global_config.retry.max_attempts.
        """
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [
                {
                    "name": "scrape_article",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {"title": "h1.title"},
                }
            ],
            "global_config": {
                "retry": {
                    "max_attempts": 8,
                    "backoff_strategy": "linear",
                }
            },
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["status"] == "pending"
        assert data["website_id"] is None

        # Verify max_retries was set correctly in the database
        job = await crawl_job_repo.get_by_id(data["id"])
        assert job is not None
        assert job.max_retries == 8  # Should use custom retry config

    async def test_create_seed_job_inline_with_browser_step(self, test_client: AsyncClient) -> None:
        """Test creating an inline config seed job with browser automation."""
        payload = {
            "seed_url": "https://dynamic.example.com/products",
            "steps": [
                {
                    "name": "crawl_products",
                    "type": "crawl",
                    "method": "browser",
                    "browser_type": "playwright",
                    "config": {
                        "wait_until": "networkidle",
                        "actions": [
                            {
                                "type": "wait",
                                "selector": ".product-list",
                                "timeout": 5000,
                            }
                        ],
                    },
                    "selectors": {"product_urls": ".product-card a"},
                }
            ],
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["seed_url"] == "https://dynamic.example.com/products"
        assert data["status"] == "pending"

    async def test_create_seed_job_inline_duplicate_step_names(
        self, test_client: AsyncClient
    ) -> None:
        """Test creating an inline config seed job with duplicate step names fails."""
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [
                {
                    "name": "duplicate_step",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {"title": "h1.title"},
                },
                {
                    "name": "duplicate_step",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {"content": ".content"},
                },
            ],
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 422  # Validation error

        error = response.json()
        assert "Step names must be unique" in str(error)

    async def test_create_seed_job_inline_invalid_url(self, test_client: AsyncClient) -> None:
        """Test creating an inline config seed job with invalid URL fails."""
        payload = {
            "seed_url": "not-a-valid-url",
            "steps": [
                {
                    "name": "scrape",
                    "type": "scrape",
                    "method": "http",
                    "selectors": {"title": "h1"},
                }
            ],
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 422  # Validation error

    async def test_create_seed_job_inline_no_steps(self, test_client: AsyncClient) -> None:
        """Test creating an inline config seed job without steps fails."""
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [],
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 422  # Validation error

    async def test_create_seed_job_inline_browser_without_type(
        self, test_client: AsyncClient
    ) -> None:
        """Test creating an inline config seed job with browser method but no browser_type fails."""
        payload = {
            "seed_url": "https://example.com/articles",
            "steps": [
                {
                    "name": "scrape",
                    "type": "scrape",
                    "method": "browser",
                    # Missing browser_type
                    "selectors": {"title": "h1"},
                }
            ],
        }

        response = await test_client.post("/api/v1/jobs/seed-inline", json=payload)
        assert response.status_code == 422  # Validation error

        error = response.json()
        assert "browser_type" in str(error).lower()
