"""Integration tests for WebSocket log streaming endpoint."""

import uuid

import pytest
from httpx import AsyncClient
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import create_app


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

        assert response.status_code == 400
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
