"""Unit tests for ScheduledJobRepository."""

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid7

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated.models import ScheduledJob
from crawler.db.repositories.scheduled_job import ScheduledJobRepository


@pytest.mark.asyncio
class TestScheduledJobRepository:
    """Unit tests for ScheduledJobRepository."""

    async def test_initialization(self) -> None:
        """Test repository initializes correctly."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        assert repo.conn == mock_conn
        assert repo._querier is not None

    async def test_deserialize_job_config_with_string(self) -> None:
        """Test _deserialize_job_config converts string to dict."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        # Create job with string job_config
        job_config_str = json.dumps({"max_depth": 5, "timeout": 30})
        job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config=job_config_str,  # String JSON
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Deserialize
        result = repo._deserialize_job_config(job)

        assert result is not None
        assert isinstance(result.job_config, dict)
        assert result.job_config == {"max_depth": 5, "timeout": 30}

    async def test_deserialize_job_config_with_dict(self) -> None:
        """Test _deserialize_job_config returns dict unchanged."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        # Create job with dict job_config
        job_config_dict = {"max_depth": 5, "timeout": 30}
        job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config=job_config_dict,  # Already a dict
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Deserialize
        result = repo._deserialize_job_config(job)

        assert result is not None
        assert result.job_config is job_config_dict  # Same object

    async def test_deserialize_job_config_with_none(self) -> None:
        """Test _deserialize_job_config returns None when input is None."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        result = repo._deserialize_job_config(None)

        assert result is None

    async def test_deserialize_job_config_handles_invalid_json(self) -> None:
        """Test _deserialize_job_config handles invalid JSON gracefully."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        # Create job with invalid JSON string
        job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config="invalid{json",  # Invalid JSON
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

        # Deserialize (should return original job)
        result = repo._deserialize_job_config(job)

        assert result is not None
        assert result.job_config == "invalid{json"  # Original value preserved

    async def test_create_serializes_job_config(self) -> None:
        """Test create serializes job_config dict to JSON."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        mock_job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config={"max_depth": 5},
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_scheduled_job = AsyncMock(return_value=mock_job)

        job_config = {"max_depth": 5, "timeout": 30}
        result = await repo.create(
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            timezone="UTC",
            job_config=job_config,
        )

        # Verify job_config was JSON serialized
        called_args = repo._querier.create_scheduled_job.call_args
        assert called_args.kwargs["job_config"] == json.dumps(job_config)
        assert result == mock_job

    async def test_create_converts_website_id_to_uuid(self) -> None:
        """Test create converts string website_id to UUID."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        mock_job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config=None,
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.create_scheduled_job = AsyncMock(return_value=mock_job)

        website_id_str = "550e8400-e29b-41d4-a716-446655440000"
        result = await repo.create(
            website_id=website_id_str,
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            timezone="UTC",
        )

        # Verify string was converted to UUID
        called_args = repo._querier.create_scheduled_job.call_args
        assert isinstance(called_args.kwargs["website_id"], UUID)
        assert str(called_args.kwargs["website_id"]) == website_id_str
        assert result == mock_job

    async def test_get_by_id_deserializes_job_config(self) -> None:
        """Test get_by_id deserializes job_config."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        # Mock job with string job_config
        job_config_str = json.dumps({"max_depth": 10})
        mock_job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config=job_config_str,
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.get_scheduled_job_by_id = AsyncMock(return_value=mock_job)

        job_id = uuid7()
        result = await repo.get_by_id(job_id)

        assert result is not None
        assert isinstance(result.job_config, dict)
        assert result.job_config == {"max_depth": 10}

    async def test_get_by_website_id_deserializes_all_jobs(self) -> None:
        """Test get_by_website_id deserializes job_config for all jobs."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        # Create mock jobs with string job_config
        mock_jobs = [
            ScheduledJob(
                id=uuid7(),
                website_id=uuid7(),
                cron_schedule="0 0 * * *",
                next_run_time=datetime.now(UTC),
                last_run_time=None,
                is_active=True,
                job_config=json.dumps({"max_depth": i}),
                timezone="UTC",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():
            for job in mock_jobs:
                yield job

        repo._querier.get_scheduled_jobs_by_website_id = MagicMock(return_value=mock_generator())

        website_id = uuid7()
        result = await repo.get_by_website_id(website_id)

        assert len(result) == 3
        assert all(isinstance(job.job_config, dict) for job in result)
        assert [job.job_config["max_depth"] for job in result] == [0, 1, 2]

    async def test_get_due_jobs_deserializes_job_config(self) -> None:
        """Test get_due_jobs deserializes job_config for all jobs."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        # Create mock jobs with string job_config
        mock_jobs = [
            ScheduledJob(
                id=uuid7(),
                website_id=uuid7(),
                cron_schedule="0 0 * * *",
                next_run_time=datetime.now(UTC),
                last_run_time=None,
                is_active=True,
                job_config=json.dumps({"priority": i}),
                timezone="UTC",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            for i in range(2)
        ]

        # Mock async generator
        async def mock_generator():
            for job in mock_jobs:
                yield job

        repo._querier.get_jobs_due_for_execution = MagicMock(return_value=mock_generator())

        cutoff_time = datetime.now(UTC)
        result = await repo.get_due_jobs(cutoff_time=cutoff_time, limit=10)

        assert len(result) == 2
        assert all(isinstance(job.job_config, dict) for job in result)
        assert [job.job_config["priority"] for job in result] == [0, 1]

    async def test_update_serializes_job_config_when_provided(self) -> None:
        """Test update serializes job_config when provided."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        mock_job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config={"updated": True},
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.update_scheduled_job = AsyncMock(return_value=mock_job)

        job_id = uuid7()
        new_config = {"updated": True, "max_depth": 15}
        result = await repo.update(job_id=job_id, job_config=new_config)

        # Verify job_config was JSON serialized
        called_args = repo._querier.update_scheduled_job.call_args
        assert called_args.kwargs["job_config"] == json.dumps(new_config)
        assert result == mock_job

    async def test_update_passes_none_for_job_config_when_not_provided(self) -> None:
        """Test update passes None for job_config when not provided."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        mock_job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 1 * *",  # Updated
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=True,
            job_config=None,
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.update_scheduled_job = AsyncMock(return_value=mock_job)

        job_id = uuid7()
        result = await repo.update(job_id=job_id, cron_schedule="0 0 1 * *")

        # Verify job_config is None
        called_args = repo._querier.update_scheduled_job.call_args
        assert called_args.kwargs["job_config"] is None
        assert result == mock_job

    async def test_count_returns_zero_when_none(self) -> None:
        """Test count returns 0 when result is None."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        repo._querier.count_scheduled_jobs = AsyncMock(return_value=None)

        result = await repo.count()

        assert result == 0

    async def test_count_returns_actual_count(self) -> None:
        """Test count returns actual count value."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        repo._querier.count_scheduled_jobs = AsyncMock(return_value=15)

        result = await repo.count(is_active=True)

        assert result == 15

    async def test_toggle_status_changes_active_flag(self) -> None:
        """Test toggle_status changes is_active flag."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        mock_job = ScheduledJob(
            id=uuid7(),
            website_id=uuid7(),
            cron_schedule="0 0 * * *",
            next_run_time=datetime.now(UTC),
            last_run_time=None,
            is_active=False,  # Toggled to False
            job_config=None,
            timezone="UTC",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        repo._querier.toggle_scheduled_job_status = AsyncMock(return_value=mock_job)

        job_id = uuid7()
        result = await repo.toggle_status(job_id=job_id, is_active=False)

        # Verify is_active was passed
        called_args = repo._querier.toggle_scheduled_job_status.call_args
        assert called_args.kwargs["is_active"] is False
        assert result == mock_job

    async def test_list_active_deserializes_job_config(self) -> None:
        """Test list_active deserializes job_config for all jobs."""
        mock_conn = MagicMock(spec=AsyncConnection)
        repo = ScheduledJobRepository(mock_conn)

        # Create mock jobs with string job_config
        mock_jobs = [
            ScheduledJob(
                id=uuid7(),
                website_id=uuid7(),
                cron_schedule="0 0 * * *",
                next_run_time=datetime.now(UTC),
                last_run_time=None,
                is_active=True,
                job_config=json.dumps({"index": i}),
                timezone="UTC",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
            for i in range(3)
        ]

        # Mock async generator
        async def mock_generator():
            for job in mock_jobs:
                yield job

        repo._querier.list_active_scheduled_jobs = MagicMock(return_value=mock_generator())

        result = await repo.list_active(limit=10, offset=0)

        assert len(result) == 3
        assert all(job.is_active for job in result)
        assert all(isinstance(job.job_config, dict) for job in result)
        assert [job.job_config["index"] for job in result] == [0, 1, 2]
