"""Unit tests for CrawlLogRepository."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import CrawlLog, LogLevelEnum
from crawler.db.repositories.crawl_log import CrawlLogRepository


@pytest.mark.asyncio
class TestCrawlLogRepository:
    """Unit tests for CrawlLogRepository."""

    async def test_initialization(self):
        """Test repository initializes correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        assert repo.conn == mock_conn
        assert repo._querier is not None

    async def test_create_converts_ids_to_uuid(self):
        """Test create converts string IDs to UUIDs."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        mock_log = CrawlLog(
            id=1,
            job_id=uuid7(),
            website_id=uuid7(),
            step_name="crawling",
            log_level=LogLevelEnum.INFO,
            message="Test log",
            context=None,
            trace_id=None,
            created_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_log = AsyncMock(return_value=mock_log)

        job_id_str = "550e8400-e29b-41d4-a716-446655440000"
        website_id_str = "660e8400-e29b-41d4-a716-446655440000"

        result = await repo.create(job_id=job_id_str, website_id=website_id_str, message="Test log")

        # Verify string IDs were converted to UUIDs
        called_args = repo._querier.create_crawl_log.call_args
        assert isinstance(called_args.kwargs["job_id"], UUID)
        assert str(called_args.kwargs["job_id"]) == job_id_str
        assert isinstance(called_args.kwargs["website_id"], UUID)
        assert str(called_args.kwargs["website_id"]) == website_id_str
        assert result == mock_log

    async def test_create_serializes_context_dict(self):
        """Test create serializes context dict to JSON."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        mock_log = CrawlLog(
            id=1,
            job_id=uuid7(),
            website_id=uuid7(),
            step_name="parsing",
            log_level=LogLevelEnum.DEBUG,
            message="Parsing data",
            context={"url": "https://example.com", "status": 200},
            trace_id=None,
            created_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_log = AsyncMock(return_value=mock_log)

        context = {"url": "https://example.com", "status": 200, "elapsed": 1.5}
        result = await repo.create(
            job_id=uuid7(),
            website_id=uuid7(),
            message="Parsing data",
            context=context,
        )

        # Verify context was JSON serialized
        called_args = repo._querier.create_crawl_log.call_args
        assert called_args.kwargs["context"] == json.dumps(context)
        assert result == mock_log

    async def test_create_handles_optional_trace_id(self):
        """Test create converts optional trace_id to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        mock_log = CrawlLog(
            id=1,
            job_id=uuid7(),
            website_id=uuid7(),
            step_name="crawling",
            log_level=LogLevelEnum.INFO,
            message="Test log",
            context=None,
            trace_id=uuid7(),
            created_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_log = AsyncMock(return_value=mock_log)

        trace_id_str = "770e8400-e29b-41d4-a716-446655440000"
        result = await repo.create(
            job_id=uuid7(),
            website_id=uuid7(),
            message="Test log",
            trace_id=trace_id_str,
        )

        # Verify trace_id was converted to UUID
        called_args = repo._querier.create_crawl_log.call_args
        assert isinstance(called_args.kwargs["trace_id"], UUID)
        assert str(called_args.kwargs["trace_id"]) == trace_id_str
        assert result == mock_log

    async def test_create_handles_none_trace_id(self):
        """Test create handles None for trace_id."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        mock_log = CrawlLog(
            id=1,
            job_id=uuid7(),
            website_id=uuid7(),
            step_name="crawling",
            log_level=LogLevelEnum.INFO,
            message="Test log",
            context=None,
            trace_id=None,
            created_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_log = AsyncMock(return_value=mock_log)

        result = await repo.create(
            job_id=uuid7(), website_id=uuid7(), message="Test log", trace_id=None
        )

        # Verify trace_id is None
        called_args = repo._querier.create_crawl_log.call_args
        assert called_args.kwargs["trace_id"] is None
        assert result == mock_log

    async def test_list_by_job_collects_async_generator(self):
        """Test list_by_job collects all results from async generator."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        # Create mock logs
        mock_logs = [
            CrawlLog(
                id=i,
                job_id=uuid7(),
                website_id=uuid7(),
                step_name=f"step{i}",
                log_level=LogLevelEnum.INFO,
                message=f"Log {i}",
                context=None,
                trace_id=None,
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():
            for log in mock_logs:
                yield log

        repo._querier.list_logs_by_job = MagicMock(return_value=mock_generator())

        job_id = uuid7()
        result = await repo.list_by_job(job_id=job_id, limit=10, offset=0)

        assert len(result) == 3
        assert all(isinstance(log, CrawlLog) for log in result)
        assert result == mock_logs

    async def test_list_by_job_filters_by_log_level(self):
        """Test list_by_job passes log_level filter."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        # Create mock error logs
        mock_logs = [
            CrawlLog(
                id=i,
                job_id=uuid7(),
                website_id=uuid7(),
                step_name=f"step{i}",
                log_level=LogLevelEnum.ERROR,
                message=f"Error {i}",
                context=None,
                trace_id=None,
                created_at=datetime.now(UTC),
            )
            for i in range(2)
        ]

        # Mock async generator
        async def mock_generator():
            for log in mock_logs:
                yield log

        repo._querier.list_logs_by_job = MagicMock(return_value=mock_generator())

        job_id = uuid7()
        result = await repo.list_by_job(
            job_id=job_id, log_level=LogLevelEnum.ERROR, limit=10, offset=0
        )

        # Verify log_level filter was passed
        called_args = repo._querier.list_logs_by_job.call_args
        assert called_args.kwargs["log_level"] == LogLevelEnum.ERROR
        assert len(result) == 2
        assert all(log.log_level == LogLevelEnum.ERROR for log in result)

    async def test_get_errors_collects_async_generator(self):
        """Test get_errors collects all error logs."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        # Create mock error logs
        mock_logs = [
            CrawlLog(
                id=i,
                job_id=uuid7(),
                website_id=uuid7(),
                step_name=f"step{i}",
                log_level=LogLevelEnum.ERROR,
                message=f"Error {i}",
                context=None,
                trace_id=None,
                created_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():
            for log in mock_logs:
                yield log

        repo._querier.get_error_logs = MagicMock(return_value=mock_generator())

        job_id = uuid7()
        result = await repo.get_errors(job_id=job_id, limit=10)

        assert len(result) == 3
        assert all(isinstance(log, CrawlLog) for log in result)
        assert all(log.log_level == LogLevelEnum.ERROR for log in result)
        assert result == mock_logs

    async def test_create_with_all_optional_parameters(self):
        """Test create with all optional parameters provided."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = CrawlLogRepository(mock_conn)

        mock_log = CrawlLog(
            id=1,
            job_id=uuid7(),
            website_id=uuid7(),
            step_name="validation",
            log_level=LogLevelEnum.WARNING,
            message="Validation warning",
            context={"field": "email", "value": "invalid"},
            trace_id=uuid7(),
            created_at=datetime.now(UTC),
        )
        repo._querier.create_crawl_log = AsyncMock(return_value=mock_log)

        context = {"field": "email", "value": "invalid"}
        result = await repo.create(
            job_id=uuid7(),
            website_id=uuid7(),
            message="Validation warning",
            log_level=LogLevelEnum.WARNING,
            step_name="validation",
            context=context,
            trace_id=uuid7(),
        )

        # Verify all parameters were passed
        called_args = repo._querier.create_crawl_log.call_args
        assert called_args.kwargs["log_level"] == LogLevelEnum.WARNING
        assert called_args.kwargs["step_name"] == "validation"
        assert called_args.kwargs["context"] == json.dumps(context)
        assert isinstance(called_args.kwargs["trace_id"], UUID)
        assert result == mock_log
