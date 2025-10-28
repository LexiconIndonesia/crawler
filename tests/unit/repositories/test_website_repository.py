"""Unit tests for WebsiteRepository."""

import json
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import StatusEnum, Website
from crawler.db.repositories.website import WebsiteRepository


@pytest.mark.asyncio
class TestWebsiteRepository:
    """Unit tests for WebsiteRepository."""

    async def test_initialization(self):
        """Test repository initializes correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        assert repo.conn == mock_conn
        assert repo._querier is not None

    async def test_create_serializes_config(self):
        """Test that create serializes config dict to JSON."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        # Mock the querier method
        mock_website = Website(
            id=uuid4(),
            name="test",
            base_url="https://example.com",
            config={"key": "value"},
            status=StatusEnum.ACTIVE,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            created_by=None,
            cron_schedule=None,
        )
        repo._querier.create_website = AsyncMock(return_value=mock_website)

        config = {"method": "api", "max_depth": 5}
        result = await repo.create(name="test", base_url="https://example.com", config=config)

        # Verify config was JSON serialized in the call
        repo._querier.create_website.assert_called_once_with(
            name="test",
            base_url="https://example.com",
            config=json.dumps(config),
            cron_schedule=None,
            created_by=None,
            status=None,
        )
        assert result == mock_website

    async def test_get_by_id_converts_string_to_uuid(self):
        """Test that get_by_id converts string ID to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid4(),
            name="test",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            created_by=None,
            cron_schedule=None,
        )
        repo._querier.get_website_by_id = AsyncMock(return_value=mock_website)

        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        result = await repo.get_by_id(uuid_str)

        # Verify string was converted to UUID
        called_args = repo._querier.get_website_by_id.call_args
        assert isinstance(called_args.kwargs["id"], UUID)
        assert str(called_args.kwargs["id"]) == uuid_str
        assert result == mock_website

    async def test_get_by_id_accepts_uuid(self):
        """Test that get_by_id accepts UUID directly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid4(),
            name="test",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            created_by=None,
            cron_schedule=None,
        )
        repo._querier.get_website_by_id = AsyncMock(return_value=mock_website)

        original_uuid = uuid4()
        result = await repo.get_by_id(original_uuid)

        # Verify UUID was passed unchanged
        called_args = repo._querier.get_website_by_id.call_args
        assert called_args.kwargs["id"] is original_uuid
        assert result == mock_website

    async def test_update_serializes_config_when_provided(self):
        """Test that update serializes config dict to JSON when provided."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid4(),
            name="test",
            base_url="https://example.com",
            config={"updated": True},
            status=StatusEnum.ACTIVE,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            created_by=None,
            cron_schedule=None,
        )
        repo._querier.update_website = AsyncMock(return_value=mock_website)

        website_id = uuid4()
        new_config = {"updated": True, "max_depth": 10}
        result = await repo.update(website_id=website_id, config=new_config)

        # Verify config was JSON serialized
        called_args = repo._querier.update_website.call_args
        assert called_args.kwargs["config"] == json.dumps(new_config)
        assert result == mock_website

    async def test_update_passes_none_for_config_when_not_provided(self):
        """Test that update passes None for config when not provided."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid4(),
            name="test",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE,
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-01T00:00:00",
            created_by=None,
            cron_schedule=None,
        )
        repo._querier.update_website = AsyncMock(return_value=mock_website)

        website_id = uuid4()
        result = await repo.update(website_id=website_id, name="new_name")

        # Verify config is None
        called_args = repo._querier.update_website.call_args
        assert called_args.kwargs["config"] is None
        assert result == mock_website

    async def test_list_collects_async_generator_results(self):
        """Test that list collects all results from async generator."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        # Create mock websites
        mock_websites = [
            Website(
                id=uuid4(),
                name=f"test{i}",
                base_url=f"https://example{i}.com",
                config={},
                status=StatusEnum.ACTIVE,
                created_at="2024-01-01T00:00:00",
                updated_at="2024-01-01T00:00:00",
                created_by=None,
                cron_schedule=None,
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():
            for website in mock_websites:
                yield website

        repo._querier.list_websites = MagicMock(return_value=mock_generator())

        result = await repo.list(limit=10, offset=0)

        assert len(result) == 3
        assert all(isinstance(w, Website) for w in result)
        assert result == mock_websites

    async def test_count_returns_zero_when_none(self):
        """Test that count returns 0 when result is None."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        repo._querier.count_websites = AsyncMock(return_value=None)

        result = await repo.count()

        assert result == 0

    async def test_count_returns_actual_count(self):
        """Test that count returns actual count value."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        repo._querier.count_websites = AsyncMock(return_value=42)

        result = await repo.count(status=StatusEnum.ACTIVE)

        assert result == 42

    async def test_delete_converts_string_to_uuid(self):
        """Test that delete converts string ID to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        repo._querier.delete_website = AsyncMock()

        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        await repo.delete(uuid_str)

        # Verify string was converted to UUID
        called_args = repo._querier.delete_website.call_args
        assert isinstance(called_args.kwargs["id"], UUID)
        assert str(called_args.kwargs["id"]) == uuid_str
