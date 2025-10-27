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
            "steps": [
                {"name": "crawl_list", "type": "crawl", "method": "api"}
            ],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["name"] == "Test Website"
        assert data["base_url"] == "https://example.com"
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
            "steps": [
                {"name": "fetch_data", "type": "crawl", "method": "api"}
            ],
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
            "steps": [
                {"name": "fetch_data", "type": "crawl", "method": "api"}
            ],
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
            "steps": [
                {"name": "test", "type": "crawl", "method": "api"}
            ],
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
            "steps": [
                {"name": "test", "type": "crawl", "method": "api"}
            ],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 400

        error = response.json()
        assert "Invalid cron expression" in error["detail"]

    async def test_create_website_invalid_url(self, test_client: AsyncClient) -> None:
        """Test creating a website with invalid base_url."""
        payload = {
            "name": "Invalid URL",
            "base_url": "not-a-valid-url",
            "steps": [
                {"name": "test", "type": "crawl", "method": "api"}
            ],
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

    async def test_create_website_browser_without_browser_type(self, test_client: AsyncClient) -> None:
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
            "steps": [
                {"name": "test", "type": "crawl", "method": "api"}
            ],
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
            "steps": [
                {"name": "test", "type": "crawl", "method": "api"}
            ],
        }

        response = await test_client.post("/api/v1/websites", json=payload)
        assert response.status_code == 201

        data = response.json()
        assert data["next_run_time"] is None
        assert data["scheduled_job_id"] is None
