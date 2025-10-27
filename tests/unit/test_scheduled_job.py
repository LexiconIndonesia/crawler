"""Unit tests for ScheduledJob schemas and repository logic."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID

import pytest
from pydantic import ValidationError

from crawler.db.repositories import ScheduledJobRepository
from crawler.schemas import (
    ScheduledJobCreate,
    ScheduledJobToggleStatus,
    ScheduledJobUpdate,
)


class TestScheduledJobSchemas:
    """Tests for ScheduledJob Pydantic schemas."""

    def test_scheduled_job_create_valid(self) -> None:
        """Test valid scheduled job creation."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "cron_schedule": "0 0 * * *",
            "next_run_time": datetime.now(UTC),
            "is_active": True,
            "job_config": {"max_depth": 5},
        }
        job = ScheduledJobCreate(**data)
        assert job.cron_schedule == "0 0 * * *"
        assert job.is_active is True
        assert job.job_config == {"max_depth": 5}

    def test_scheduled_job_create_minimal(self) -> None:
        """Test scheduled job creation with minimal fields."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "cron_schedule": "0 0 * * *",
            "next_run_time": datetime.now(UTC),
        }
        job = ScheduledJobCreate(**data)
        assert job.is_active is True  # default
        assert job.job_config == {}  # default

    def test_scheduled_job_invalid_cron_too_few_parts(self) -> None:
        """Test scheduled job with invalid cron expression (too few parts)."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "cron_schedule": "minute hour day",  # Only 3 parts (but > 9 chars)
            "next_run_time": datetime.now(UTC),
        }
        with pytest.raises(ValidationError) as exc_info:
            ScheduledJobCreate(**data)
        # The validation error should mention parts count
        errors = str(exc_info.value)
        assert "5 or 6 parts" in errors

    def test_scheduled_job_invalid_cron_too_many_parts(self) -> None:
        """Test scheduled job with invalid cron expression (too many parts)."""
        data = {
            "website_id": "123e4567-e89b-12d3-a456-426614174000",
            "cron_schedule": "0 0 * * * * *",  # 7 parts
            "next_run_time": datetime.now(UTC),
        }
        with pytest.raises(ValidationError) as exc_info:
            ScheduledJobCreate(**data)
        assert "must have 5 or 6 parts" in str(exc_info.value)

    def test_scheduled_job_valid_cron_expressions(self) -> None:
        """Test various valid cron expressions."""
        valid_crons = [
            "0 0 * * *",  # Daily at midnight
            "0 12 * * 1",  # Every Monday at noon
            "*/15 * * * *",  # Every 15 minutes
            "0 0 1,15 * *",  # Bi-weekly (1st and 15th)
            "0 0 * * 1-5",  # Weekdays only
            "0 0 1 * * 2025",  # With year
        ]
        for cron in valid_crons:
            data = {
                "website_id": "123e4567-e89b-12d3-a456-426614174000",
                "cron_schedule": cron,
                "next_run_time": datetime.now(UTC),
            }
            job = ScheduledJobCreate(**data)
            assert job.cron_schedule == cron

    def test_scheduled_job_update_partial(self) -> None:
        """Test partial scheduled job update."""
        data = {"is_active": False, "job_config": {"timeout": 60}}
        update = ScheduledJobUpdate(**data)
        assert update.is_active is False
        assert update.job_config == {"timeout": 60}
        assert update.cron_schedule is None  # Not provided

    def test_scheduled_job_toggle_status(self) -> None:
        """Test scheduled job status toggle schema."""
        data = {"is_active": False}
        toggle = ScheduledJobToggleStatus(**data)
        assert toggle.is_active is False

        data = {"is_active": True}
        toggle = ScheduledJobToggleStatus(**data)
        assert toggle.is_active is True


class TestScheduledJobRepository:
    """Unit tests for ScheduledJobRepository logic."""

    @pytest.fixture
    def mock_connection(self) -> MagicMock:
        """Create a mock database connection."""
        return MagicMock()

    @pytest.fixture
    def mock_querier(self) -> AsyncMock:
        """Create a mock sqlc querier."""
        return AsyncMock()

    @pytest.fixture
    def repository(
        self, mock_connection: MagicMock, mock_querier: AsyncMock
    ) -> ScheduledJobRepository:
        """Create a ScheduledJobRepository with mocked dependencies."""
        repo = ScheduledJobRepository(mock_connection)
        repo._querier = mock_querier
        return repo

    async def test_create_serializes_job_config(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test that create() properly serializes job_config to JSON."""
        website_id = "123e4567-e89b-12d3-a456-426614174000"
        next_run = datetime.now(UTC)
        job_config = {"max_depth": 5, "timeout": 30}

        await repository.create(
            website_id=website_id,
            cron_schedule="0 0 * * *",
            next_run_time=next_run,
            job_config=job_config,
        )

        # Verify the querier was called with JSON-serialized config
        mock_querier.create_scheduled_job.assert_called_once()
        call_kwargs = mock_querier.create_scheduled_job.call_args.kwargs
        assert call_kwargs["website_id"] == UUID(website_id)
        assert call_kwargs["job_config"] == '{"max_depth": 5, "timeout": 30}'

    async def test_create_handles_none_job_config(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test that create() handles None job_config."""
        website_id = "123e4567-e89b-12d3-a456-426614174000"
        next_run = datetime.now(UTC)

        await repository.create(
            website_id=website_id,
            cron_schedule="0 0 * * *",
            next_run_time=next_run,
            job_config=None,
        )

        # Verify the querier was called with None
        mock_querier.create_scheduled_job.assert_called_once()
        call_kwargs = mock_querier.create_scheduled_job.call_args.kwargs
        assert call_kwargs["job_config"] is None

    async def test_update_serializes_job_config(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test that update() properly serializes job_config to JSON."""
        job_id = "987fcdeb-51a2-43f1-b4e5-123456789abc"
        job_config = {"new_field": "value"}

        await repository.update(job_id=job_id, job_config=job_config)

        # Verify the querier was called with JSON-serialized config
        mock_querier.update_scheduled_job.assert_called_once()
        call_kwargs = mock_querier.update_scheduled_job.call_args.kwargs
        assert call_kwargs["job_config"] == '{"new_field": "value"}'

    async def test_get_by_id_converts_string_to_uuid(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test that get_by_id() converts string ID to UUID."""
        job_id = "987fcdeb-51a2-43f1-b4e5-123456789abc"

        await repository.get_by_id(job_id)

        # Verify the querier was called with UUID
        mock_querier.get_scheduled_job_by_id.assert_called_once()
        call_kwargs = mock_querier.get_scheduled_job_by_id.call_args.kwargs
        assert isinstance(call_kwargs["id"], UUID)
        assert str(call_kwargs["id"]) == job_id

    async def test_get_by_id_accepts_uuid(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test that get_by_id() accepts UUID objects."""
        job_id = UUID("987fcdeb-51a2-43f1-b4e5-123456789abc")

        await repository.get_by_id(job_id)

        # Verify the querier was called with UUID
        mock_querier.get_scheduled_job_by_id.assert_called_once()
        call_kwargs = mock_querier.get_scheduled_job_by_id.call_args.kwargs
        assert call_kwargs["id"] == job_id

    async def test_toggle_status(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test toggle_status() calls querier correctly."""
        job_id = "987fcdeb-51a2-43f1-b4e5-123456789abc"

        await repository.toggle_status(job_id, is_active=False)

        # Verify the querier was called correctly
        mock_querier.toggle_scheduled_job_status.assert_called_once()
        call_kwargs = mock_querier.toggle_scheduled_job_status.call_args.kwargs
        assert call_kwargs["is_active"] is False
        assert str(call_kwargs["id"]) == job_id

    async def test_count_handles_none_filters(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test count() handles None filters correctly."""
        mock_querier.count_scheduled_jobs.return_value = 5

        result = await repository.count(website_id=None, is_active=None)

        # Verify the querier was called with None values
        mock_querier.count_scheduled_jobs.assert_called_once()
        call_kwargs = mock_querier.count_scheduled_jobs.call_args.kwargs
        assert call_kwargs["website_id"] is None
        assert call_kwargs["is_active"] is None
        assert result == 5

    async def test_count_returns_zero_on_none_result(
        self, repository: ScheduledJobRepository, mock_querier: AsyncMock
    ) -> None:
        """Test count() returns 0 when querier returns None."""
        mock_querier.count_scheduled_jobs.return_value = None

        result = await repository.count()

        assert result == 0
