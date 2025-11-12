"""Unit tests for memory monitoring service."""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import psutil
import pytest

from crawler.services.memory_monitor import MemoryLevel, MemoryMonitor


@pytest.fixture
def mock_browser_pool() -> MagicMock:
    """Create a mock browser pool."""
    pool = MagicMock()
    pool._initialized = True
    pool._lock = AsyncMock()
    pool._lock.__aenter__ = AsyncMock()
    pool._lock.__aexit__ = AsyncMock()
    pool._browsers = []
    return pool


@pytest.fixture
def memory_monitor(mock_browser_pool: MagicMock) -> MemoryMonitor:
    """Create a memory monitor instance with default settings."""
    return MemoryMonitor(
        browser_pool=mock_browser_pool,
        check_interval=1.0,
        healthy_threshold=70.0,
        warning_threshold=85.0,
        critical_threshold=95.0,
    )


class TestMemoryLevel:
    """Tests for MemoryLevel enum."""

    def test_memory_levels_defined(self) -> None:
        """Test that all memory levels are defined."""
        assert MemoryLevel.HEALTHY == "healthy"
        assert MemoryLevel.WARNING == "warning"
        assert MemoryLevel.CRITICAL == "critical"
        assert MemoryLevel.DANGER == "danger"


class TestMemoryMonitor:
    """Tests for MemoryMonitor class."""

    def test_init_default_values(self) -> None:
        """Test monitor initialization with default values."""
        monitor = MemoryMonitor()
        assert monitor.browser_pool is None
        assert monitor.check_interval == 30.0
        assert monitor.healthy_threshold == 70.0
        assert monitor.warning_threshold == 85.0
        assert monitor.critical_threshold == 95.0
        assert monitor._running is False
        assert monitor._last_level == MemoryLevel.HEALTHY

    def test_init_custom_values(self, mock_browser_pool: MagicMock) -> None:
        """Test monitor initialization with custom values."""
        monitor = MemoryMonitor(
            browser_pool=mock_browser_pool,
            check_interval=10.0,
            healthy_threshold=60.0,
            warning_threshold=80.0,
            critical_threshold=90.0,
        )
        assert monitor.browser_pool == mock_browser_pool
        assert monitor.check_interval == 10.0
        assert monitor.healthy_threshold == 60.0
        assert monitor.warning_threshold == 80.0
        assert monitor.critical_threshold == 90.0

    async def test_start_monitor(self, memory_monitor: MemoryMonitor) -> None:
        """Test starting the memory monitor."""
        assert memory_monitor._running is False

        await memory_monitor.start()

        assert memory_monitor._running is True
        assert memory_monitor._monitor_task is not None

        # Clean up
        await memory_monitor.stop()

    async def test_start_already_running(self, memory_monitor: MemoryMonitor) -> None:
        """Test starting monitor when already running logs warning."""
        await memory_monitor.start()
        assert memory_monitor._running is True

        # Try to start again
        with patch("crawler.services.memory_monitor.logger") as mock_logger:
            await memory_monitor.start()
            mock_logger.warning.assert_called_once_with("memory_monitor_already_running")

        await memory_monitor.stop()

    async def test_stop_monitor(self, memory_monitor: MemoryMonitor) -> None:
        """Test stopping the memory monitor."""
        await memory_monitor.start()
        assert memory_monitor._running is True

        await memory_monitor.stop()

        assert memory_monitor._running is False

    async def test_stop_not_running(self, memory_monitor: MemoryMonitor) -> None:
        """Test stopping monitor when not running logs warning."""
        assert memory_monitor._running is False

        with patch("crawler.services.memory_monitor.logger") as mock_logger:
            await memory_monitor.stop()
            mock_logger.warning.assert_called_once_with("memory_monitor_not_running")

    def test_get_memory_level_healthy(self, memory_monitor: MemoryMonitor) -> None:
        """Test getting memory level for healthy usage (<70%)."""
        assert memory_monitor._get_memory_level(50.0) == MemoryLevel.HEALTHY
        assert memory_monitor._get_memory_level(69.9) == MemoryLevel.HEALTHY

    def test_get_memory_level_warning(self, memory_monitor: MemoryMonitor) -> None:
        """Test getting memory level for warning usage (70-85%)."""
        assert memory_monitor._get_memory_level(70.0) == MemoryLevel.WARNING
        assert memory_monitor._get_memory_level(80.0) == MemoryLevel.WARNING
        assert memory_monitor._get_memory_level(84.9) == MemoryLevel.WARNING

    def test_get_memory_level_critical(self, memory_monitor: MemoryMonitor) -> None:
        """Test getting memory level for critical usage (85-95%)."""
        assert memory_monitor._get_memory_level(85.0) == MemoryLevel.CRITICAL
        assert memory_monitor._get_memory_level(90.0) == MemoryLevel.CRITICAL
        assert memory_monitor._get_memory_level(94.9) == MemoryLevel.CRITICAL

    def test_get_memory_level_danger(self, memory_monitor: MemoryMonitor) -> None:
        """Test getting memory level for danger usage (>95%)."""
        assert memory_monitor._get_memory_level(95.0) == MemoryLevel.DANGER
        assert memory_monitor._get_memory_level(99.9) == MemoryLevel.DANGER
        assert memory_monitor._get_memory_level(100.0) == MemoryLevel.DANGER

    @patch("crawler.services.memory_monitor.memory_alerts_total")
    @patch("crawler.services.memory_monitor.logger")
    def test_emit_alert(
        self, mock_logger: Mock, mock_alerts_counter: Mock, memory_monitor: MemoryMonitor
    ) -> None:
        """Test emitting memory alert."""
        memory_monitor._last_level = MemoryLevel.HEALTHY

        memory_monitor._emit_alert(MemoryLevel.WARNING, 75.0, "system")

        mock_alerts_counter.labels.assert_called_once_with(level="warning", type="system")
        mock_alerts_counter.labels.return_value.inc.assert_called_once()
        mock_logger.warning.assert_called_once_with(
            "memory_alert",
            level="warning",
            percent=75.0,
            type="system",
            previous_level="healthy",
        )

    @patch("crawler.services.memory_monitor.psutil.virtual_memory")
    @patch("crawler.services.memory_monitor.system_memory_usage_percent")
    @patch("crawler.services.memory_monitor.system_memory_used_bytes")
    @patch("crawler.services.memory_monitor.system_memory_available_bytes")
    async def test_check_memory_system_only(
        self,
        mock_available_metric: Mock,
        mock_used_metric: Mock,
        mock_percent_metric: Mock,
        mock_virtual_memory: Mock,
        memory_monitor: MemoryMonitor,
    ) -> None:
        """Test checking memory with system only (no browser pool)."""
        # Mock system memory
        mock_vm = MagicMock()
        mock_vm.percent = 65.0
        mock_vm.used = 8_000_000_000  # 8GB
        mock_vm.available = 4_000_000_000  # 4GB
        mock_virtual_memory.return_value = mock_vm

        # Set browser pool to None
        memory_monitor.browser_pool = None

        status = await memory_monitor.check_memory()

        # Verify status
        assert status.system_percent == 65.0
        assert status.system_used_bytes == 8_000_000_000
        assert status.system_available_bytes == 4_000_000_000
        assert status.level == MemoryLevel.HEALTHY
        assert len(status.browser_memory) == 0

        # Verify metrics updated
        mock_percent_metric.set.assert_called_once_with(65.0)
        mock_used_metric.set.assert_called_once_with(8_000_000_000)
        mock_available_metric.set.assert_called_once_with(4_000_000_000)

    @patch("crawler.services.memory_monitor.psutil.virtual_memory")
    @patch("crawler.services.memory_monitor.system_memory_usage_percent")
    @patch("crawler.services.memory_monitor.system_memory_used_bytes")
    @patch("crawler.services.memory_monitor.system_memory_available_bytes")
    async def test_check_memory_level_transition(
        self,
        mock_available_metric: Mock,
        mock_used_metric: Mock,
        mock_percent_metric: Mock,
        mock_virtual_memory: Mock,
        memory_monitor: MemoryMonitor,
    ) -> None:
        """Test memory check with level transition triggers alert."""
        # Mock system memory at warning level
        mock_vm = MagicMock()
        mock_vm.percent = 75.0
        mock_vm.used = 9_000_000_000
        mock_vm.available = 3_000_000_000
        mock_virtual_memory.return_value = mock_vm

        memory_monitor.browser_pool = None

        with patch.object(memory_monitor, "_emit_alert") as mock_emit:
            status = await memory_monitor.check_memory()

            # Verify alert emitted for level transition
            mock_emit.assert_called_once_with(MemoryLevel.WARNING, 75.0, "system")
            assert status.level == MemoryLevel.WARNING
            assert memory_monitor._last_level == MemoryLevel.WARNING

    @patch("crawler.services.memory_monitor.psutil.virtual_memory")
    async def test_check_memory_no_alert_same_level(
        self, mock_virtual_memory: Mock, memory_monitor: MemoryMonitor
    ) -> None:
        """Test memory check with same level does not trigger alert."""
        # Mock system memory at healthy level
        mock_vm = MagicMock()
        mock_vm.percent = 65.0
        mock_vm.used = 8_000_000_000
        mock_vm.available = 4_000_000_000
        mock_virtual_memory.return_value = mock_vm

        memory_monitor.browser_pool = None
        memory_monitor._last_level = MemoryLevel.HEALTHY

        with patch.object(memory_monitor, "_emit_alert") as mock_emit:
            await memory_monitor.check_memory()

            # No alert should be emitted
            mock_emit.assert_not_called()

    def test_get_browser_pid_no_impl_obj(self, memory_monitor: MemoryMonitor) -> None:
        """Test getting browser PID when no _impl_obj available."""
        browser_instance = MagicMock()
        browser_instance.browser = MagicMock(spec=[])  # No _impl_obj attribute

        pid = memory_monitor._get_browser_pid(browser_instance)

        assert pid is None

    def test_get_browser_pid_success(self, memory_monitor: MemoryMonitor) -> None:
        """Test successfully getting browser PID."""
        # Mock browser with nested structure
        mock_proc = MagicMock()
        mock_proc.pid = 12345

        mock_transport = MagicMock()
        mock_transport._proc = mock_proc

        mock_connection = MagicMock()
        mock_connection._transport = mock_transport

        mock_impl = MagicMock()
        mock_impl._connection = mock_connection

        browser_instance = MagicMock()
        browser_instance.browser._impl_obj = mock_impl

        pid = memory_monitor._get_browser_pid(browser_instance)

        assert pid == 12345

    @patch("crawler.services.memory_monitor.psutil.virtual_memory")
    @patch("crawler.services.memory_monitor.psutil.Process")
    async def test_check_browser_memory_success(
        self, mock_process_class: Mock, mock_virtual_memory: Mock, memory_monitor: MemoryMonitor
    ) -> None:
        """Test checking browser memory successfully."""
        # Mock system memory
        mock_vm = MagicMock()
        mock_vm.percent = 65.0
        mock_vm.used = 8_000_000_000
        mock_vm.available = 4_000_000_000
        mock_virtual_memory.return_value = mock_vm

        # Mock browser instance
        mock_browser = MagicMock()
        mock_browser_instance = MagicMock()
        mock_browser_instance.browser = mock_browser

        # Setup browser pool with one browser
        memory_monitor.browser_pool._browsers = [mock_browser_instance]

        # Mock PID extraction
        with patch.object(memory_monitor, "_get_browser_pid", return_value=12345):
            # Mock process memory
            mock_memory_info = MagicMock()
            mock_memory_info.rss = 500_000_000  # 500MB
            mock_process = MagicMock()
            mock_process.memory_info.return_value = mock_memory_info
            mock_process_class.return_value = mock_process

            status = await memory_monitor.check_memory()

            # Verify browser memory tracked
            assert 0 in status.browser_memory
            assert status.browser_memory[0] == 500_000_000

    @patch("crawler.services.memory_monitor.psutil.virtual_memory")
    async def test_check_browser_memory_no_pid(
        self, mock_virtual_memory: Mock, memory_monitor: MemoryMonitor
    ) -> None:
        """Test checking browser memory when PID unavailable."""
        # Mock system memory
        mock_vm = MagicMock()
        mock_vm.percent = 65.0
        mock_vm.used = 8_000_000_000
        mock_vm.available = 4_000_000_000
        mock_virtual_memory.return_value = mock_vm

        # Mock browser instance
        mock_browser_instance = MagicMock()
        memory_monitor.browser_pool._browsers = [mock_browser_instance]

        # Mock PID extraction to return None
        with patch.object(memory_monitor, "_get_browser_pid", return_value=None):
            status = await memory_monitor.check_memory()

            # Browser memory should be empty
            assert len(status.browser_memory) == 0

    @patch("crawler.services.memory_monitor.psutil.virtual_memory")
    @patch("crawler.services.memory_monitor.psutil.Process")
    async def test_check_browser_memory_process_not_found(
        self, mock_process_class: Mock, mock_virtual_memory: Mock, memory_monitor: MemoryMonitor
    ) -> None:
        """Test checking browser memory when process not found."""
        # Mock system memory
        mock_vm = MagicMock()
        mock_vm.percent = 65.0
        mock_vm.used = 8_000_000_000
        mock_vm.available = 4_000_000_000
        mock_virtual_memory.return_value = mock_vm

        # Mock browser instance
        mock_browser_instance = MagicMock()
        memory_monitor.browser_pool._browsers = [mock_browser_instance]

        # Mock PID extraction
        with patch.object(memory_monitor, "_get_browser_pid", return_value=12345):
            # Mock process not found
            mock_process_class.side_effect = psutil.NoSuchProcess(12345)

            status = await memory_monitor.check_memory()

            # Browser memory should be empty
            assert len(status.browser_memory) == 0

    async def test_check_browser_memory_pool_not_initialized(
        self, memory_monitor: MemoryMonitor
    ) -> None:
        """Test checking browser memory when pool not initialized."""
        memory_monitor.browser_pool._initialized = False

        browser_memory = await memory_monitor._check_browser_memory()

        assert len(browser_memory) == 0

    def test_get_status(self, memory_monitor: MemoryMonitor) -> None:
        """Test getting monitor status."""
        memory_monitor._running = True
        memory_monitor._last_level = MemoryLevel.WARNING

        status = memory_monitor.get_status()

        assert status["running"] is True
        assert status["check_interval"] == 1.0
        assert status["healthy_threshold"] == 70.0
        assert status["warning_threshold"] == 85.0
        assert status["critical_threshold"] == 95.0
        assert status["last_level"] == "warning"
