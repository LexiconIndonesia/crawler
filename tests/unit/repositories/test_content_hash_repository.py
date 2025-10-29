"""Unit tests for ContentHashRepository."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import ContentHash
from crawler.db.repositories.content_hash import ContentHashRepository


@pytest.mark.asyncio
class TestContentHashRepository:
    """Unit tests for ContentHashRepository."""

    async def test_initialization(self):
        """Test repository initializes correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ContentHashRepository(mock_conn)

        assert repo.conn == mock_conn
        assert repo._querier is not None

    async def test_upsert_converts_string_page_id_to_uuid(self):
        """Test upsert converts string page ID to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ContentHashRepository(mock_conn)

        mock_content_hash = ContentHash(
            content_hash="hash123",
            first_seen_page_id=uuid7(),
            occurrence_count=1,
            last_seen_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.upsert_content_hash = AsyncMock(return_value=mock_content_hash)

        page_id_str = "550e8400-e29b-41d4-a716-446655440000"
        result = await repo.upsert(content_hash_value="hash123", first_seen_page_id=page_id_str)

        # Verify string was converted to UUID
        called_args = repo._querier.upsert_content_hash.call_args
        assert isinstance(called_args.kwargs["first_seen_page_id"], UUID)
        assert str(called_args.kwargs["first_seen_page_id"]) == page_id_str
        assert called_args.kwargs["content_hash"] == "hash123"
        assert result == mock_content_hash

    async def test_upsert_accepts_uuid_page_id(self):
        """Test upsert accepts UUID page ID directly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ContentHashRepository(mock_conn)

        mock_content_hash = ContentHash(
            content_hash="hash123",
            first_seen_page_id=uuid7(),
            occurrence_count=1,
            last_seen_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.upsert_content_hash = AsyncMock(return_value=mock_content_hash)

        page_id = uuid7()
        result = await repo.upsert(content_hash_value="hash123", first_seen_page_id=page_id)

        # Verify UUID was passed unchanged
        called_args = repo._querier.upsert_content_hash.call_args
        assert called_args.kwargs["first_seen_page_id"] is page_id
        assert result == mock_content_hash

    async def test_upsert_handles_none_page_id(self):
        """Test upsert handles None for first_seen_page_id."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ContentHashRepository(mock_conn)

        mock_content_hash = ContentHash(
            content_hash="hash123",
            first_seen_page_id=None,
            occurrence_count=2,
            last_seen_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.upsert_content_hash = AsyncMock(return_value=mock_content_hash)

        result = await repo.upsert(content_hash_value="hash123", first_seen_page_id=None)

        # Verify None was passed unchanged
        called_args = repo._querier.upsert_content_hash.call_args
        assert called_args.kwargs["first_seen_page_id"] is None
        assert called_args.kwargs["content_hash"] == "hash123"
        assert result == mock_content_hash

    async def test_get_returns_content_hash(self):
        """Test get returns content hash record."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ContentHashRepository(mock_conn)

        mock_content_hash = ContentHash(
            content_hash="hash123",
            first_seen_page_id=uuid7(),
            occurrence_count=5,
            last_seen_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.get_content_hash = AsyncMock(return_value=mock_content_hash)

        result = await repo.get("hash123")

        # Verify content_hash parameter
        called_args = repo._querier.get_content_hash.call_args
        assert called_args.kwargs["content_hash"] == "hash123"
        assert result == mock_content_hash

    async def test_get_returns_none_when_not_found(self):
        """Test get returns None when content hash not found."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ContentHashRepository(mock_conn)

        repo._querier.get_content_hash = AsyncMock(return_value=None)

        result = await repo.get("nonexistent_hash")

        assert result is None

    async def test_upsert_increments_occurrence_count(self):
        """Test upsert behavior for incrementing occurrence count."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ContentHashRepository(mock_conn)

        # First call returns count=1
        first_result = ContentHash(
            content_hash="hash123",
            first_seen_page_id=uuid7(),
            occurrence_count=1,
            last_seen_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )

        # Second call returns count=2 (simulating increment)
        second_result = ContentHash(
            content_hash="hash123",
            first_seen_page_id=first_result.first_seen_page_id,
            occurrence_count=2,
            last_seen_at=datetime.now(UTC),
            created_at=first_result.created_at,
        )

        repo._querier.upsert_content_hash = AsyncMock(side_effect=[first_result, second_result])

        page_id = uuid7()

        # First upsert
        result1 = await repo.upsert(content_hash_value="hash123", first_seen_page_id=page_id)
        assert result1.occurrence_count == 1

        # Second upsert (simulating duplicate)
        result2 = await repo.upsert(
            content_hash_value="hash123", first_seen_page_id=None
        )  # None because already exists
        assert result2.occurrence_count == 2
        assert result2.first_seen_page_id == first_result.first_seen_page_id  # Unchanged
