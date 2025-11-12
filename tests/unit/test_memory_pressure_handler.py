"""Unit tests for memory pressure handler."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from crawler.db.generated.models import StatusEnum
from crawler.services.memory_monitor import MemoryLevel, MemoryStatus
from crawler.services.memory_pressure_handler import (
    MemoryPressureHandler,
    PressureAction,
    PressureState,
)


@pytest.fixture
def mock_memory_monitor() -> MagicMock:
    """Create a mock memory monitor."""
    monitor = MagicMock()
    monitor._last_level = MemoryLevel.HEALTHY
    return monitor


@pytest.fixture
def mock_browser_pool() -> MagicMock:
    """Create a mock browser pool."""
    pool = MagicMock()
    pool._initialized = True
    pool._lock = AsyncMock()
    pool._lock.__aenter__ = AsyncMock()
    pool._lock.__aexit__ = AsyncMock()
    pool._browsers = []
    pool._launch_browser = AsyncMock()
    return pool


@pytest.fixture
def mock_settings() -> MagicMock:
    """Create a mock settings instance."""
    settings = MagicMock()
    settings.redis_url = "redis://localhost:6379"
    settings.database_url = "postgresql://localhost/test"
    return settings


@pytest.fixture
def memory_status_healthy() -> MemoryStatus:
    """Create a healthy memory status."""
    return MemoryStatus(
        timestamp=datetime.now(UTC),
        system_percent=60.0,
        system_used_bytes=6_000_000_000,
        system_available_bytes=4_000_000_000,
        level=MemoryLevel.HEALTHY,
        browser_memory={},
    )


@pytest.fixture
def memory_status_warning() -> MemoryStatus:
    """Create a warning memory status."""
    return MemoryStatus(
        timestamp=datetime.now(UTC),
        system_percent=75.0,
        system_used_bytes=7_500_000_000,
        system_available_bytes=2_500_000_000,
        level=MemoryLevel.WARNING,
        browser_memory={},
    )


@pytest.fixture
def memory_status_critical() -> MemoryStatus:
    """Create a critical memory status."""
    return MemoryStatus(
        timestamp=datetime.now(UTC),
        system_percent=90.0,
        system_used_bytes=9_000_000_000,
        system_available_bytes=1_000_000_000,
        level=MemoryLevel.CRITICAL,
        browser_memory={},
    )


@pytest.fixture
def memory_status_danger() -> MemoryStatus:
    """Create a danger memory status."""
    return MemoryStatus(
        timestamp=datetime.now(UTC),
        system_percent=97.0,
        system_used_bytes=9_700_000_000,
        system_available_bytes=300_000_000,
        level=MemoryLevel.DANGER,
        browser_memory={},
    )


@pytest.fixture
def pressure_handler(
    mock_memory_monitor: MagicMock,
    mock_browser_pool: MagicMock,
    mock_settings: MagicMock,
) -> MemoryPressureHandler:
    """Create a pressure handler with all dependencies."""
    return MemoryPressureHandler(
        memory_monitor=mock_memory_monitor,
        browser_pool=mock_browser_pool,
        settings=mock_settings,
        min_idle_time_seconds=60.0,
        low_priority_threshold=3,
    )


class TestPressureState:
    """Tests for PressureState enum."""

    def test_pressure_states_defined(self) -> None:
        """Test that all pressure states are defined."""
        assert PressureState.NORMAL == "normal"
        assert PressureState.WARNING == "warning"
        assert PressureState.CRITICAL == "critical"
        assert PressureState.DANGER == "danger"


class TestPressureAction:
    """Tests for PressureAction enum."""

    def test_pressure_actions_defined(self) -> None:
        """Test that all pressure actions are defined."""
        assert PressureAction.PAUSE_JOBS == "pause_jobs"
        assert PressureAction.RESUME_JOBS == "resume_jobs"
        assert PressureAction.CLOSE_IDLE_CONTEXTS == "close_idle_contexts"
        assert PressureAction.CANCEL_LOW_PRIORITY_JOBS == "cancel_low_priority_jobs"
        assert PressureAction.RESTART_BROWSERS == "restart_browsers"


class TestMemoryPressureHandler:
    """Tests for MemoryPressureHandler class."""

    def test_init_default_values(
        self, mock_memory_monitor: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Test handler initialization with default values."""
        handler = MemoryPressureHandler(memory_monitor=mock_memory_monitor, settings=mock_settings)
        assert handler.memory_monitor == mock_memory_monitor
        assert handler.settings == mock_settings
        assert handler.browser_pool is None
        assert handler.min_idle_time_seconds == 60.0
        assert handler.low_priority_threshold == 3
        assert handler._current_state == PressureState.NORMAL
        assert handler._jobs_paused is False

    def test_init_custom_values(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test handler initialization with custom values."""
        assert pressure_handler.browser_pool is not None
        assert pressure_handler.settings is not None
        assert pressure_handler.min_idle_time_seconds == 60.0
        assert pressure_handler.low_priority_threshold == 3

    def test_get_pressure_state_healthy(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test mapping healthy memory level to pressure state."""
        state = pressure_handler._get_pressure_state(MemoryLevel.HEALTHY)
        assert state == PressureState.NORMAL

    def test_get_pressure_state_warning(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test mapping warning memory level to pressure state."""
        state = pressure_handler._get_pressure_state(MemoryLevel.WARNING)
        assert state == PressureState.WARNING

    def test_get_pressure_state_critical(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test mapping critical memory level to pressure state."""
        state = pressure_handler._get_pressure_state(MemoryLevel.CRITICAL)
        assert state == PressureState.CRITICAL

    def test_get_pressure_state_danger(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test mapping danger memory level to pressure state."""
        state = pressure_handler._get_pressure_state(MemoryLevel.DANGER)
        assert state == PressureState.DANGER

    async def test_handle_memory_status_no_change(
        self, pressure_handler: MemoryPressureHandler, memory_status_healthy: MemoryStatus
    ) -> None:
        """Test handling memory status with no state change."""
        # Handler starts in NORMAL state, memory is HEALTHY (maps to NORMAL)
        actions = await pressure_handler.handle_memory_status(memory_status_healthy)
        assert len(actions) == 0
        assert pressure_handler._current_state == PressureState.NORMAL

    async def test_handle_memory_status_to_critical(
        self, pressure_handler: MemoryPressureHandler, memory_status_critical: MemoryStatus
    ) -> None:
        """Test handling transition to critical state."""
        actions = await pressure_handler.handle_memory_status(memory_status_critical)

        # Should pause jobs and close idle contexts
        assert len(actions) == 2
        assert any(a.action == PressureAction.PAUSE_JOBS for a in actions)
        assert any(a.action == PressureAction.CLOSE_IDLE_CONTEXTS for a in actions)
        assert pressure_handler._current_state == PressureState.CRITICAL
        assert pressure_handler._jobs_paused is True

    async def test_handle_memory_status_to_danger(
        self, pressure_handler: MemoryPressureHandler, memory_status_danger: MemoryStatus
    ) -> None:
        """Test handling transition to danger state."""
        actions = await pressure_handler.handle_memory_status(memory_status_danger)

        # Should cancel low priority jobs, restart browsers, and pause jobs
        assert len(actions) == 3
        assert any(a.action == PressureAction.CANCEL_LOW_PRIORITY_JOBS for a in actions)
        assert any(a.action == PressureAction.RESTART_BROWSERS for a in actions)
        assert any(a.action == PressureAction.PAUSE_JOBS for a in actions)
        assert pressure_handler._current_state == PressureState.DANGER

    async def test_handle_memory_status_recovery(
        self,
        pressure_handler: MemoryPressureHandler,
        memory_status_critical: MemoryStatus,
        memory_status_healthy: MemoryStatus,
    ) -> None:
        """Test recovery from critical to healthy state."""
        # First transition to critical
        await pressure_handler.handle_memory_status(memory_status_critical)
        assert pressure_handler._jobs_paused is True

        # Then recover to healthy
        actions = await pressure_handler.handle_memory_status(memory_status_healthy)

        # Should resume jobs
        assert len(actions) == 1
        assert actions[0].action == PressureAction.RESUME_JOBS
        assert pressure_handler._current_state == PressureState.NORMAL
        assert pressure_handler._jobs_paused is False

    async def test_pause_jobs_success(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test successfully pausing jobs."""
        response = await pressure_handler._pause_jobs()

        assert response.action == PressureAction.PAUSE_JOBS
        assert response.success is True
        assert response.details["paused"] is True
        assert pressure_handler._jobs_paused is True

    async def test_pause_jobs_already_paused(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test pausing jobs when already paused."""
        pressure_handler._jobs_paused = True

        response = await pressure_handler._pause_jobs()

        assert response.action == PressureAction.PAUSE_JOBS
        assert response.success is False
        assert response.details["reason"] == "already_paused"

    async def test_resume_jobs_success(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test successfully resuming jobs."""
        pressure_handler._jobs_paused = True

        response = await pressure_handler._resume_jobs()

        assert response.action == PressureAction.RESUME_JOBS
        assert response.success is True
        assert response.details["resumed"] is True
        assert pressure_handler._jobs_paused is False

    async def test_resume_jobs_not_paused(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test resuming jobs when not paused."""
        response = await pressure_handler._resume_jobs()

        assert response.action == PressureAction.RESUME_JOBS
        assert response.success is False
        assert response.details["reason"] == "not_paused"

    async def test_close_idle_contexts_no_pool(
        self, mock_memory_monitor: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Test closing idle contexts with no browser pool."""
        handler = MemoryPressureHandler(
            memory_monitor=mock_memory_monitor, browser_pool=None, settings=mock_settings
        )

        response = await handler._close_idle_contexts()

        assert response.action == PressureAction.CLOSE_IDLE_CONTEXTS
        assert response.success is False
        assert response.details["reason"] == "browser_pool_unavailable"

    async def test_close_idle_contexts_success(
        self, pressure_handler: MemoryPressureHandler, mock_browser_pool: MagicMock
    ) -> None:
        """Test closing idle contexts successfully."""
        # Mock the public close_idle_contexts method
        mock_browser_pool.close_idle_contexts = AsyncMock(return_value=3)

        response = await pressure_handler._close_idle_contexts()

        assert response.action == PressureAction.CLOSE_IDLE_CONTEXTS
        assert response.success is True
        assert response.details["contexts_closed"] == 3
        mock_browser_pool.close_idle_contexts.assert_called_once_with(
            min_idle_seconds=pressure_handler.min_idle_time_seconds
        )

    @patch("crawler.services.memory_pressure_handler.get_redis")
    @patch("crawler.services.memory_pressure_handler.get_db")
    async def test_cancel_low_priority_jobs_no_jobs(
        self,
        mock_get_db: Mock,
        mock_get_redis: Mock,
        mock_memory_monitor: MagicMock,
        mock_settings: MagicMock,
    ) -> None:
        """Test cancelling jobs when no pending jobs exist."""
        # Mock database session and connection
        mock_connection = MagicMock()
        mock_session = MagicMock()
        mock_session.connection = AsyncMock(return_value=mock_connection)

        async def db_generator():
            yield mock_session

        mock_get_db.return_value = db_generator()

        # Mock Redis client
        mock_redis_client = MagicMock()

        async def redis_generator():
            yield mock_redis_client

        mock_get_redis.return_value = redis_generator()

        # Mock repository with no pending jobs
        with patch(
            "crawler.services.memory_pressure_handler.CrawlJobRepository"
        ) as mock_repo_class:
            mock_repo = MagicMock()
            mock_repo.get_pending = AsyncMock(return_value=[])
            mock_repo_class.return_value = mock_repo

            handler = MemoryPressureHandler(
                memory_monitor=mock_memory_monitor, settings=mock_settings
            )
            response = await handler._cancel_low_priority_jobs()

            assert response.action == PressureAction.CANCEL_LOW_PRIORITY_JOBS
            assert response.success is True
            assert response.details["jobs_cancelled"] == 0

    @patch("crawler.services.memory_pressure_handler.get_redis")
    @patch("crawler.services.memory_pressure_handler.get_db")
    @patch("crawler.services.memory_pressure_handler.CrawlJobRepository")
    @patch("crawler.services.memory_pressure_handler.JobCancellationFlag")
    async def test_cancel_low_priority_jobs_success(
        self,
        mock_flag_class: Mock,
        mock_repo_class: Mock,
        mock_get_db: Mock,
        mock_get_redis: Mock,
        pressure_handler: MemoryPressureHandler,
    ) -> None:
        """Test successfully cancelling low priority jobs."""
        # Mock pending jobs
        mock_job1 = MagicMock()
        mock_job1.id = "job-1"
        mock_job1.priority = 1  # Low priority
        mock_job1.status = StatusEnum.PENDING

        mock_job2 = MagicMock()
        mock_job2.id = "job-2"
        mock_job2.priority = 5  # Normal priority
        mock_job2.status = StatusEnum.PENDING

        # Mock repository
        mock_repo = MagicMock()
        mock_repo.get_pending = AsyncMock(return_value=[mock_job1, mock_job2])
        mock_repo.cancel = AsyncMock()
        mock_repo_class.return_value = mock_repo

        # Mock database session and connection
        mock_connection = MagicMock()
        mock_session = MagicMock()
        mock_session.connection = AsyncMock(return_value=mock_connection)

        async def db_generator():
            yield mock_session

        mock_get_db.return_value = db_generator()

        # Mock Redis client and cancellation flag
        mock_redis_client = MagicMock()

        async def redis_generator():
            yield mock_redis_client

        mock_get_redis.return_value = redis_generator()

        mock_flag = MagicMock()
        mock_flag.set_cancellation = AsyncMock()
        mock_flag_class.return_value = mock_flag

        response = await pressure_handler._cancel_low_priority_jobs()

        assert response.action == PressureAction.CANCEL_LOW_PRIORITY_JOBS
        assert response.success is True
        assert response.details["jobs_cancelled"] == 1  # Only job1 (priority <= 3)
        assert response.details["priority_threshold"] == 3

        # Verify cancellation flag was set
        mock_flag.set_cancellation.assert_called_once()

        # Verify job was cancelled in database
        mock_repo.cancel.assert_called_once()

    async def test_restart_browsers_no_pool(
        self, mock_memory_monitor: MagicMock, mock_settings: MagicMock
    ) -> None:
        """Test restarting browsers with no browser pool."""
        handler = MemoryPressureHandler(
            memory_monitor=mock_memory_monitor, browser_pool=None, settings=mock_settings
        )

        response = await handler._restart_browsers()

        assert response.action == PressureAction.RESTART_BROWSERS
        assert response.success is False
        assert response.details["reason"] == "browser_pool_unavailable"

    async def test_restart_browsers_success(
        self, pressure_handler: MemoryPressureHandler, mock_browser_pool: MagicMock
    ) -> None:
        """Test successfully restarting browsers."""
        # Mock the public restart_idle_browsers method
        mock_browser_pool.restart_idle_browsers = AsyncMock(return_value=2)

        response = await pressure_handler._restart_browsers()

        assert response.action == PressureAction.RESTART_BROWSERS
        assert response.success is True
        assert response.details["browsers_restarted"] == 2
        mock_browser_pool.restart_idle_browsers.assert_called_once_with(max_count=2)

    async def test_restart_browsers_skip_active(
        self, pressure_handler: MemoryPressureHandler, mock_browser_pool: MagicMock
    ) -> None:
        """Test that browsers with active contexts are skipped."""
        # Mock the public restart_idle_browsers method returning 0 (none restarted)
        mock_browser_pool.restart_idle_browsers = AsyncMock(return_value=0)

        response = await pressure_handler._restart_browsers()

        assert response.action == PressureAction.RESTART_BROWSERS
        assert response.success is True
        assert response.details["browsers_restarted"] == 0  # None restarted
        mock_browser_pool.restart_idle_browsers.assert_called_once_with(max_count=2)

    def test_get_status(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test getting handler status."""
        pressure_handler._current_state = PressureState.CRITICAL
        pressure_handler._jobs_paused = True

        status = pressure_handler.get_status()

        assert status["current_state"] == "critical"
        assert status["jobs_paused"] is True
        assert status["min_idle_time_seconds"] == 60.0
        assert status["low_priority_threshold"] == 3

    async def test_get_action_history(
        self,
        pressure_handler: MemoryPressureHandler,
        memory_status_critical: MemoryStatus,
        memory_status_healthy: MemoryStatus,
    ) -> None:
        """Test getting action history."""
        # Perform some actions via handle_memory_status
        await pressure_handler.handle_memory_status(memory_status_critical)
        await pressure_handler.handle_memory_status(memory_status_healthy)

        history = pressure_handler.get_action_history(limit=10)

        # Should have recorded actions: pause_jobs, close_idle_contexts, resume_jobs
        assert len(history) >= 2
        assert any(h["action"] == "pause_jobs" for h in history)
        assert any(h["action"] == "resume_jobs" for h in history)

    def test_is_jobs_paused(self, pressure_handler: MemoryPressureHandler) -> None:
        """Test checking if jobs are paused."""
        assert pressure_handler.is_jobs_paused is False

        pressure_handler._jobs_paused = True
        assert pressure_handler.is_jobs_paused is True

    async def test_action_history_limit(
        self,
        pressure_handler: MemoryPressureHandler,
        memory_status_critical: MemoryStatus,
        memory_status_danger: MemoryStatus,
    ) -> None:
        """Test that action history is limited to 100 entries."""
        # Add more than 100 actions by cycling between critical and danger states
        for i in range(40):
            # Critical state: 2 actions (pause_jobs, close_idle_contexts)
            await pressure_handler.handle_memory_status(memory_status_critical)
            pressure_handler._current_state = PressureState.NORMAL  # Reset state
            # Danger state: 3 actions (cancel_jobs, restart_browsers, pause_jobs)
            await pressure_handler.handle_memory_status(memory_status_danger)
            pressure_handler._current_state = PressureState.NORMAL  # Reset state

        # 40 cycles * 5 actions/cycle = 200 actions, should be limited to 100
        assert len(pressure_handler._action_history) == 100
