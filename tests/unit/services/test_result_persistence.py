"""Unit tests for result persistence service."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from crawler.db.generated.models import CrawledPage
from crawler.services.result_persistence import ResultPersistenceService
from crawler.services.step_execution_context import StepExecutionContext, StepResult


class TestResultPersistenceService:
    """Tests for ResultPersistenceService class."""

    @pytest.fixture
    def mock_conn(self) -> MagicMock:
        """Create mock database connection."""
        return MagicMock()

    @pytest.fixture
    def service(self, mock_conn: MagicMock) -> ResultPersistenceService:
        """Create result persistence service with mock connection."""
        service = ResultPersistenceService(mock_conn)
        # Mock internal repositories/services to avoid DB/computation in unit tests
        service.content_hash_repo = MagicMock()
        service.content_hash_repo.find_similar = AsyncMock(return_value=[])
        service.content_hash_repo.upsert_with_simhash = AsyncMock()
        service.content_hash_repo.upsert = AsyncMock()

        service.normalizer = MagicMock()
        service.normalizer.normalize_for_hash.return_value = "normalized"
        return service

    @pytest.fixture
    def context(self) -> StepExecutionContext:
        """Create execution context with test data."""
        context = StepExecutionContext(
            job_id="test-job-123", website_id="test-website-456", variables={}
        )
        return context

    async def test_persist_workflow_results_with_no_steps(
        self, service: ResultPersistenceService, context: StepExecutionContext
    ) -> None:
        """Test persisting workflow with no step results."""
        stats = await service.persist_workflow_results(
            job_id="test-job", website_id="test-website", context=context
        )

        assert stats["pages_saved"] == 0
        assert stats["pages_failed"] == 0

    async def test_persist_workflow_results_skips_failed_steps(
        self, service: ResultPersistenceService, context: StepExecutionContext
    ) -> None:
        """Test that failed steps are skipped during persistence."""
        # Add failed step
        context.add_result(StepResult(step_name="failed_step", error="Something went wrong"))

        stats = await service.persist_workflow_results(
            job_id="test-job", website_id="test-website", context=context
        )

        assert stats["pages_saved"] == 0
        assert stats["pages_failed"] == 0

    async def test_persist_single_page_result(
        self, service: ResultPersistenceService, context: StepExecutionContext, mock_conn: MagicMock
    ) -> None:
        """Test persisting single page result."""
        # Add successful step with single page
        context.add_result(
            StepResult(
                step_name="test_step",
                extracted_data={
                    "_url": "https://example.com",
                    "_content": "<html>test</html>",
                    "title": "Test Page",
                    "description": "Test description",
                },
            )
        )

        # Mock repository methods
        mock_page_repo = MagicMock()
        mock_page_repo.get_by_content_hash = AsyncMock(return_value=None)
        mock_page_repo.create = AsyncMock(
            return_value=CrawledPage(
                id=uuid4(),
                website_id=uuid4(),
                job_id=uuid4(),
                url="https://example.com",
                url_hash="test_hash",
                content_hash="test_content_hash",
                crawled_at=datetime.now(UTC),
                title="Test Page",
                extracted_content='{"title": "Test Page", "description": "Test description"}',
                metadata=None,
                gcs_html_path=None,
                gcs_documents=None,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
                is_duplicate=False,
                duplicate_of=None,
                similarity_score=None,
            )
        )
        mock_page_repo.mark_as_duplicate = AsyncMock()

        with patch.object(service, "page_repo", mock_page_repo):
            stats = await service.persist_workflow_results(
                job_id="test-job", website_id="test-website", context=context
            )

        assert stats["pages_saved"] == 1
        assert stats["pages_failed"] == 0
        mock_page_repo.create.assert_called_once()
        # Verify Simhash upsert was called
        service.content_hash_repo.upsert_with_simhash.assert_called_once()

    async def test_persist_multiple_pages_from_items(
        self, service: ResultPersistenceService, context: StepExecutionContext, mock_conn: MagicMock
    ) -> None:
        """Test persisting multiple pages from items array."""
        # Add successful step with items array
        context.add_result(
            StepResult(
                step_name="scrape_step",
                extracted_data={
                    "items": [
                        {
                            "_url": "https://example.com/page1",
                            "_content": "<html>page1</html>",
                            "title": "Page 1",
                        },
                        {
                            "_url": "https://example.com/page2",
                            "_content": "<html>page2</html>",
                            "title": "Page 2",
                        },
                    ]
                },
            )
        )

        # Mock repository
        mock_page_repo = MagicMock()
        mock_page_repo.get_by_content_hash = AsyncMock(return_value=None)
        mock_page_repo.create = AsyncMock(
            side_effect=[
                CrawledPage(
                    id=uuid4(),
                    website_id=uuid4(),
                    job_id=uuid4(),
                    url="https://example.com/page1",
                    url_hash="hash1",
                    content_hash="content_hash1",
                    crawled_at=datetime.now(UTC),
                    title="Page 1",
                    extracted_content='{"title": "Page 1"}',
                    metadata=None,
                    gcs_html_path=None,
                    gcs_documents=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    is_duplicate=False,
                    duplicate_of=None,
                    similarity_score=None,
                ),
                CrawledPage(
                    id=uuid4(),
                    website_id=uuid4(),
                    job_id=uuid4(),
                    url="https://example.com/page2",
                    url_hash="hash2",
                    content_hash="content_hash2",
                    crawled_at=datetime.now(UTC),
                    title="Page 2",
                    extracted_content='{"title": "Page 2"}',
                    metadata=None,
                    gcs_html_path=None,
                    gcs_documents=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    is_duplicate=False,
                    duplicate_of=None,
                    similarity_score=None,
                ),
            ]
        )

        with patch.object(service, "page_repo", mock_page_repo):
            stats = await service.persist_workflow_results(
                job_id="test-job", website_id="test-website", context=context
            )

        assert stats["pages_saved"] == 2
        assert stats["pages_failed"] == 0
        assert mock_page_repo.create.call_count == 2

    async def test_duplicate_detection(
        self, service: ResultPersistenceService, context: StepExecutionContext
    ) -> None:
        """Test duplicate page detection by content hash."""
        # Add page result
        context.add_result(
            StepResult(
                step_name="test_step",
                extracted_data={
                    "_url": "https://example.com/new",
                    "_content": "<html>duplicate content</html>",
                    "title": "New Page",
                },
            )
        )

        # Mock repository - existing page with same content
        existing_page = CrawledPage(
            id=uuid4(),
            website_id=uuid4(),
            job_id=uuid4(),
            url="https://example.com/original",
            url_hash="original_hash",
            content_hash="same_content_hash",
            crawled_at=datetime.now(UTC),
            title="Original Page",
            extracted_content='{"title": "Original Page"}',
            metadata=None,
            gcs_html_path=None,
            gcs_documents=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=None,
        )

        new_page = CrawledPage(
            id=uuid4(),
            website_id=uuid4(),
            job_id=uuid4(),
            url="https://example.com/new",
            url_hash="new_hash",
            content_hash="same_content_hash",
            crawled_at=datetime.now(UTC),
            title="New Page",
            extracted_content='{"title": "New Page"}',
            metadata=None,
            gcs_html_path=None,
            gcs_documents=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=None,
        )

        mock_page_repo = MagicMock()
        mock_page_repo.get_by_content_hash = AsyncMock(return_value=existing_page)
        mock_page_repo.create = AsyncMock(return_value=new_page)
        mock_page_repo.mark_as_duplicate = AsyncMock()

        with patch.object(service, "page_repo", mock_page_repo):
            stats = await service.persist_workflow_results(
                job_id="test-job", website_id="test-website", context=context
            )

        assert stats["pages_saved"] == 1
        mock_page_repo.mark_as_duplicate.assert_called_once()

    async def test_persist_detects_fuzzy_duplicate(
        self, service: ResultPersistenceService, context: StepExecutionContext
    ) -> None:
        """Test fuzzy duplicate detection using Simhash."""
        # Add page result
        context.add_result(
            StepResult(
                step_name="test_step",
                extracted_data={
                    "_url": "https://example.com/fuzzy",
                    "_content": "<html>similar content</html>",
                    "title": "Fuzzy Page",
                },
            )
        )

        # Mock page repo
        mock_page_repo = MagicMock()
        mock_page_repo.get_by_content_hash = AsyncMock(
            side_effect=[
                None,  # First call: check for exact duplicate (not found)
                CrawledPage(  # Second call: get page for fuzzy match
                    id=uuid4(),
                    website_id=uuid4(),
                    job_id=uuid4(),
                    url="https://example.com/original",
                    url_hash="hash",
                    content_hash="original_hash",
                    crawled_at=datetime.now(UTC),
                    title="Original",
                    extracted_content="{}",
                    metadata=None,
                    gcs_html_path=None,
                    gcs_documents=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    is_duplicate=False,
                    duplicate_of=None,
                    similarity_score=None,
                ),
            ]
        )

        saved_page = CrawledPage(
            id=uuid4(),
            website_id=uuid4(),
            job_id=uuid4(),
            url="https://example.com/fuzzy",
            url_hash="new_hash",
            content_hash="new_content_hash",
            crawled_at=datetime.now(UTC),
            title="Fuzzy Page",
            extracted_content='{"title": "Fuzzy Page"}',
            metadata=None,
            gcs_html_path=None,
            gcs_documents=None,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            is_duplicate=False,
            duplicate_of=None,
            similarity_score=None,
        )
        mock_page_repo.create = AsyncMock(return_value=saved_page)
        mock_page_repo.mark_as_duplicate = AsyncMock()

        # Mock content hash repo to return similar content
        mock_match = MagicMock()
        mock_match.content_hash = "original_hash"
        mock_match.hamming_distance = 2  # Very similar
        service.content_hash_repo.find_similar = AsyncMock(return_value=[mock_match])

        with patch.object(service, "page_repo", mock_page_repo):
            stats = await service.persist_workflow_results(
                job_id="test-job", website_id="test-website", context=context
            )

        assert stats["pages_saved"] == 1

        # Verify fuzzy duplicate detection flow
        service.content_hash_repo.find_similar.assert_called_once()
        mock_page_repo.mark_as_duplicate.assert_called_once()

        # Check similarity score calculation: (1 - 2/64) * 100 = 96
        call_args = mock_page_repo.mark_as_duplicate.call_args
        assert call_args.kwargs["similarity_score"] == 96
        assert call_args.kwargs["duplicate_of"] is not None

    async def test_hash_url_generates_consistent_hash(
        self, service: ResultPersistenceService
    ) -> None:
        """Test URL hashing is consistent."""
        url = "https://example.com/test"

        hash1 = service._hash_url(url)
        hash2 = service._hash_url(url)

        assert hash1 == hash2
        assert len(hash1) == 64  # SHA256 hex digest length

    async def test_hash_content_handles_string(self, service: ResultPersistenceService) -> None:
        """Test content hashing handles string content."""
        content = "<html>test content</html>"

        content_hash = service._hash_content(content)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64  # SHA256 hex digest

    async def test_hash_content_handles_dict(self, service: ResultPersistenceService) -> None:
        """Test content hashing handles dict content."""
        content = {"title": "Test", "body": "Content"}

        content_hash = service._hash_content(content)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64

    async def test_hash_content_handles_none(self, service: ResultPersistenceService) -> None:
        """Test content hashing handles None content."""
        content_hash = service._hash_content(None)

        assert isinstance(content_hash, str)
        assert len(content_hash) == 64

    async def test_hash_content_same_dict_produces_same_hash(
        self, service: ResultPersistenceService
    ) -> None:
        """Test that identical dicts produce identical hashes (order-independent)."""
        content1 = {"b": "value2", "a": "value1"}
        content2 = {"a": "value1", "b": "value2"}

        hash1 = service._hash_content(content1)
        hash2 = service._hash_content(content2)

        # Should be same because keys are sorted during JSON serialization
        assert hash1 == hash2

    async def test_extract_pages_from_single_page_result(
        self, service: ResultPersistenceService
    ) -> None:
        """Test extracting pages from single page result."""
        extracted_data = {
            "_url": "https://example.com",
            "_content": "<html>test</html>",
            "title": "Test",
        }

        pages = service._extract_pages_from_step("test_step", extracted_data)

        assert len(pages) == 1
        assert pages[0]["_url"] == "https://example.com"
        assert pages[0]["title"] == "Test"

    async def test_extract_pages_from_items_array(self, service: ResultPersistenceService) -> None:
        """Test extracting pages from items array."""
        extracted_data = {
            "items": [
                {"_url": "https://example.com/1", "title": "Page 1"},
                {"_url": "https://example.com/2", "title": "Page 2"},
            ]
        }

        pages = service._extract_pages_from_step("scrape_step", extracted_data)

        assert len(pages) == 2
        assert pages[0]["_url"] == "https://example.com/1"
        assert pages[1]["_url"] == "https://example.com/2"

    async def test_extract_pages_skips_items_without_url(
        self, service: ResultPersistenceService
    ) -> None:
        """Test that items without _url field are skipped."""
        extracted_data = {
            "items": [
                {"_url": "https://example.com/1", "title": "Page 1"},
                {"title": "Page 2"},  # Missing _url
            ]
        }

        pages = service._extract_pages_from_step("scrape_step", extracted_data)

        assert len(pages) == 1  # Only page with _url
        assert pages[0]["_url"] == "https://example.com/1"

    async def test_extract_pages_returns_empty_for_no_data(
        self, service: ResultPersistenceService
    ) -> None:
        """Test extracting pages from empty data."""
        pages = service._extract_pages_from_step("test_step", None)
        assert len(pages) == 0

        pages = service._extract_pages_from_step("test_step", {})
        assert len(pages) == 0

    async def test_persist_handles_save_errors(
        self, service: ResultPersistenceService, context: StepExecutionContext
    ) -> None:
        """Test that save errors are caught and counted."""
        # Add pages
        context.add_result(
            StepResult(
                step_name="test_step",
                extracted_data={
                    "items": [
                        {"_url": "https://example.com/1", "title": "Page 1"},
                        {"_url": "https://example.com/2", "title": "Page 2"},
                    ]
                },
            )
        )

        # Mock repo to fail on second page
        mock_page_repo = MagicMock()
        mock_page_repo.get_by_content_hash = AsyncMock(return_value=None)
        mock_page_repo.create = AsyncMock(
            side_effect=[
                CrawledPage(
                    id=uuid4(),
                    website_id=uuid4(),
                    job_id=uuid4(),
                    url="https://example.com/1",
                    url_hash="hash1",
                    content_hash="content1",
                    crawled_at=datetime.now(UTC),
                    title="Page 1",
                    extracted_content='{"title": "Page 1"}',
                    metadata=None,
                    gcs_html_path=None,
                    gcs_documents=None,
                    created_at=datetime.now(UTC),
                    updated_at=datetime.now(UTC),
                    is_duplicate=False,
                    duplicate_of=None,
                    similarity_score=None,
                ),
                Exception("Database error"),  # Second save fails
            ]
        )

        service.content_hash_repo.upsert_with_simhash = AsyncMock()
        service.normalizer.normalize_for_hash.return_value = "normalized"

        with patch.object(service, "page_repo", mock_page_repo):
            stats = await service.persist_workflow_results(
                job_id="test-job", website_id="test-website", context=context
            )

        assert stats["pages_saved"] == 1
        assert stats["pages_failed"] == 1
