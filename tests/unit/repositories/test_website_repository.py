"""Unit tests for WebsiteRepository."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import StatusEnum, Website
from crawler.db.repositories.website import WebsiteRepository


@pytest.mark.asyncio
class TestWebsiteRepository:
    """Unit tests for WebsiteRepository."""

    async def test_initialization(self) -> None:
        """Test repository initializes correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        assert repo.conn == mock_conn
        assert repo._querier is not None

    async def test_create_serializes_config(self) -> None:
        """Test that create serializes config dict to JSON."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        # Mock the querier method
        mock_website = Website(
            id=uuid7(),
            name="test",
            base_url="https://example.com",
            config={"key": "value"},
            status=StatusEnum.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
            cron_schedule=None,
        )
        repo._querier.create_website = AsyncMock(return_value=mock_website)  # type: ignore[method-assign]

        config = {"method": "api", "max_depth": 5}
        result = await repo.create(name="test", base_url="https://example.com", config=config)

        # Verify config was JSON serialized in the call and defaults were applied
        repo._querier.create_website.assert_called_once_with(
            name="test",
            base_url="https://example.com",
            config=json.dumps(config),
            cron_schedule="0 0 1,15 * *",  # Default bi-weekly schedule
            created_by=None,
            status=StatusEnum.ACTIVE,  # Default status enum
        )
        assert result == mock_website

    async def test_get_by_id_converts_string_to_uuid(self) -> None:
        """Test that get_by_id converts string ID to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid7(),
            name="test",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
            cron_schedule=None,
        )
        repo._querier.get_website_by_id = AsyncMock(return_value=mock_website)  # type: ignore[method-assign]

        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        result = await repo.get_by_id(uuid_str)

        # Verify string was converted to UUID
        called_args = repo._querier.get_website_by_id.call_args
        assert isinstance(called_args.kwargs["id"], UUID)
        assert str(called_args.kwargs["id"]) == uuid_str
        assert result == mock_website

    async def test_get_by_id_accepts_uuid(self) -> None:
        """Test that get_by_id accepts UUID directly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid7(),
            name="test",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
            cron_schedule=None,
        )
        repo._querier.get_website_by_id = AsyncMock(return_value=mock_website)  # type: ignore[method-assign]

        original_uuid = uuid7()
        result = await repo.get_by_id(original_uuid)

        # Verify UUID was passed unchanged
        called_args = repo._querier.get_website_by_id.call_args
        assert called_args.kwargs["id"] is original_uuid
        assert result == mock_website

    async def test_update_serializes_config_when_provided(self) -> None:
        """Test that update serializes config dict to JSON when provided."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid7(),
            name="test",
            base_url="https://example.com",
            config={"updated": True},
            status=StatusEnum.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
            cron_schedule=None,
        )
        repo._querier.update_website = AsyncMock(return_value=mock_website)  # type: ignore[method-assign]

        website_id = uuid7()
        new_config = {"updated": True, "max_depth": 10}
        result = await repo.update(website_id=website_id, config=new_config)

        # Verify config was JSON serialized
        called_args = repo._querier.update_website.call_args
        assert called_args.kwargs["config"] == json.dumps(new_config)
        assert result == mock_website

    async def test_update_passes_none_for_config_when_not_provided(self) -> None:
        """Test that update passes None for config when not provided."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        mock_website = Website(
            id=uuid7(),
            name="test",
            base_url="https://example.com",
            config={},
            status=StatusEnum.ACTIVE,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            created_by=None,
            deleted_at=None,
            cron_schedule=None,
        )
        repo._querier.update_website = AsyncMock(return_value=mock_website)  # type: ignore[method-assign]

        website_id = uuid7()
        result = await repo.update(website_id=website_id, name="new_name")

        # Verify config is None
        called_args = repo._querier.update_website.call_args
        assert called_args.kwargs["config"] is None
        assert result == mock_website

    async def test_list_collects_async_generator_results(self) -> None:
        """Test that list collects all results from async generator."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        # Create mock websites
        now = datetime.now(UTC)
        mock_websites = [
            Website(
                id=uuid7(),
                name=f"test{i}",
                base_url=f"https://example{i}.com",
                config={},
                status=StatusEnum.ACTIVE,
                created_at=now,
                updated_at=now,
                created_by=None,
                deleted_at=None,
                cron_schedule=None,
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():  # type: ignore[no-untyped-def]
            for website in mock_websites:
                yield website

        repo._querier.list_websites = MagicMock(return_value=mock_generator())  # type: ignore[method-assign]

        result = await repo.list(limit=10, offset=0)

        assert len(result) == 3
        assert all(isinstance(w, Website) for w in result)
        assert result == mock_websites

    async def test_count_returns_zero_when_none(self) -> None:
        """Test that count returns 0 when result is None."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        repo._querier.count_websites = AsyncMock(return_value=None)  # type: ignore[method-assign]

        result = await repo.count()

        assert result == 0

    async def test_count_returns_actual_count(self) -> None:
        """Test that count returns actual count value."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        repo._querier.count_websites = AsyncMock(return_value=42)  # type: ignore[method-assign]

        result = await repo.count(status=StatusEnum.ACTIVE)

        assert result == 42

    async def test_delete_converts_string_to_uuid(self) -> None:
        """Test that delete converts string ID to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = WebsiteRepository(mock_conn)

        repo._querier.delete_website = AsyncMock()  # type: ignore[method-assign]

        uuid_str = "550e8400-e29b-41d4-a716-446655440000"
        await repo.delete(uuid_str)

        # Verify string was converted to UUID
        called_args = repo._querier.delete_website.call_args
        assert isinstance(called_args.kwargs["id"], UUID)
        assert str(called_args.kwargs["id"]) == uuid_str
