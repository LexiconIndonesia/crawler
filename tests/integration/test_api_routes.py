"""Integration tests for API routes.

These tests require running PostgreSQL and Redis instances.
Run with: make test-integration
"""

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
