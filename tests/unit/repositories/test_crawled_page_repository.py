"""Unit tests for CrawledPageRepository."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import CrawledPage
from crawler.db.repositories.crawled_page import CrawledPageRepository


@pytest.mark.asyncio
class TestCrawledPageRepository:
    """Unit tests for CrawledPageRepository."""

    async def test_initialization(self) -> None:
        """Test repository initializes correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawledPageRepository(mock_conn)

        assert repo.conn == mock_conn
        assert repo._querier is not None

    async def test_create_serializes_metadata_and_gcs_documents(self) -> None:
        """Test create serializes metadata and gcs_documents to JSON."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawledPageRepository(mock_conn)

        mock_page = CrawledPage(
            id=uuid7(),
            website_id=uuid7(),
            job_id=uuid7(),
            url="https://example.com/page",
            url_hash="hash123",
            content_hash="contenthash456",
            title="Test Page",
            extracted_content="Some content",
            metadata={"key": "value"},
            gcs_html_path="gs://bucket/file.html",
            gcs_documents={"doc1": "path1"},
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=None,
            crawled_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.create_crawled_page = AsyncMock(return_value=mock_page)

        metadata = {"page_type": "article", "author": "John Doe"}
        gcs_documents = {"pdf": "gs://bucket/doc.pdf", "image": "gs://bucket/img.png"}

        result = await repo.create(
            website_id=uuid7(),
            job_id=uuid7(),
            url="https://example.com/page",
            url_hash="hash123",
            content_hash="contenthash456",
            crawled_at=datetime.now(UTC),
            metadata=metadata,
            gcs_documents=gcs_documents,
        )

        # Verify JSON serialization
        called_args = repo._querier.create_crawled_page.call_args
        params = called_args[0][0]  # CreateCrawledPageParams
        assert params.metadata == json.dumps(metadata)
        assert params.gcs_documents == json.dumps(gcs_documents)
        assert result == mock_page

    async def test_create_converts_ids_to_uuid(self) -> None:
        """Test create converts string IDs to UUIDs."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawledPageRepository(mock_conn)

        mock_page = CrawledPage(
            id=uuid7(),
            website_id=uuid7(),
            job_id=uuid7(),
            url="https://example.com/page",
            url_hash="hash123",
            content_hash="contenthash456",
            title=None,
            extracted_content=None,
            metadata=None,
            gcs_html_path=None,
            gcs_documents=None,
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=None,
            crawled_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.create_crawled_page = AsyncMock(return_value=mock_page)

        website_id_str = "550e8400-e29b-41d4-a716-446655440000"
        job_id_str = "660e8400-e29b-41d4-a716-446655440000"

        result = await repo.create(
            website_id=website_id_str,
            job_id=job_id_str,
            url="https://example.com/page",
            url_hash="hash123",
            content_hash="contenthash456",
            crawled_at=datetime.now(UTC),
        )

        # Verify string IDs were converted to UUIDs
        called_args = repo._querier.create_crawled_page.call_args
        params = called_args[0][0]
        assert isinstance(params.website_id, UUID)
        assert str(params.website_id) == website_id_str
        assert isinstance(params.job_id, UUID)
        assert str(params.job_id) == job_id_str
        assert result == mock_page

    async def test_get_by_id_converts_string_to_uuid(self) -> None:
        """Test get_by_id converts string ID to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawledPageRepository(mock_conn)

        mock_page = CrawledPage(
            id=uuid7(),
            website_id=uuid7(),
            job_id=uuid7(),
            url="https://example.com/page",
            url_hash="hash123",
            content_hash="contenthash456",
            title=None,
            extracted_content=None,
            metadata=None,
            gcs_html_path=None,
            gcs_documents=None,
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=None,
            crawled_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.get_crawled_page_by_id = AsyncMock(return_value=mock_page)

        page_id_str = "550e8400-e29b-41d4-a716-446655440000"
        result = await repo.get_by_id(page_id_str)

        # Verify string was converted to UUID
        called_args = repo._querier.get_crawled_page_by_id.call_args
        assert isinstance(called_args.kwargs["id"], UUID)
        assert str(called_args.kwargs["id"]) == page_id_str
        assert result == mock_page

    async def test_list_by_job_collects_async_generator(self) -> None:
        """Test list_by_job collects all results from async generator."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawledPageRepository(mock_conn)

        # Create mock pages
        mock_pages = [
            CrawledPage(
                id=uuid7(),
                website_id=uuid7(),
                job_id=uuid7(),
                url=f"https://example.com/page{i}",
                url_hash=f"hash{i}",
                content_hash=f"content{i}",
                title=None,
                extracted_content=None,
                metadata=None,
                gcs_html_path=None,
                gcs_documents=None,
                is_duplicate=False,
                duplicate_of=None,
                similarity_score=None,
                crawled_at=datetime.now(UTC),
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():
            for page in mock_pages:
                yield page

        repo._querier.list_pages_by_job = MagicMock(return_value=mock_generator())

        job_id = uuid7()
        result = await repo.list_by_job(job_id=job_id, limit=10, offset=0)

        assert len(result) == 3
        assert all(isinstance(p, CrawledPage) for p in result)
        assert result == mock_pages

    async def test_mark_as_duplicate_converts_optional_uuid(self) -> None:
        """Test mark_as_duplicate converts optional duplicate_of to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawledPageRepository(mock_conn)

        mock_page = CrawledPage(
            id=uuid7(),
            website_id=uuid7(),
            job_id=uuid7(),
            url="https://example.com/page",
            url_hash="hash123",
            content_hash="contenthash456",
            title=None,
            extracted_content=None,
            metadata=None,
            gcs_html_path=None,
            gcs_documents=None,
            is_duplicate=True,
            duplicate_of=uuid7(),
            similarity_score=95,
            crawled_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.mark_page_as_duplicate = AsyncMock(return_value=mock_page)

        page_id = uuid7()
        duplicate_of_str = "550e8400-e29b-41d4-a716-446655440000"

        result = await repo.mark_as_duplicate(
            page_id=page_id, duplicate_of=duplicate_of_str, similarity_score=95
        )

        # Verify duplicate_of was converted to UUID
        called_args = repo._querier.mark_page_as_duplicate.call_args
        assert isinstance(called_args.kwargs["duplicate_of"], UUID)
        assert str(called_args.kwargs["duplicate_of"]) == duplicate_of_str
        assert called_args.kwargs["similarity_score"] == 95
        assert result == mock_page

    async def test_mark_as_duplicate_handles_none_duplicate_of(self) -> None:
        """Test mark_as_duplicate handles None for duplicate_of."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawledPageRepository(mock_conn)

        mock_page = CrawledPage(
            id=uuid7(),
            website_id=uuid7(),
            job_id=uuid7(),
            url="https://example.com/page",
            url_hash="hash123",
            content_hash="contenthash456",
            title=None,
            extracted_content=None,
            metadata=None,
            gcs_html_path=None,
            gcs_documents=None,
            is_duplicate=True,
            duplicate_of=None,
            similarity_score=None,
            crawled_at=datetime.now(UTC),
            created_at=datetime.now(UTC),
        )
        repo._querier.mark_page_as_duplicate = AsyncMock(return_value=mock_page)

        page_id = uuid7()
        result = await repo.mark_as_duplicate(page_id=page_id, duplicate_of=None)

        # Verify duplicate_of is None
        called_args = repo._querier.mark_page_as_duplicate.call_args
        assert called_args.kwargs["duplicate_of"] is None
        assert result == mock_page
