"""Memory monitoring service for system and browser process memory tracking.

Monitors system memory usage and per-browser memory consumption with configurable
thresholds and alerting. Emits Prometheus metrics for observability.
"""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import psutil

from crawler.core.logging import get_logger
from crawler.core.metrics import (
    browser_memory_usage_bytes,
    memory_alerts_total,
    system_memory_available_bytes,
    system_memory_usage_percent,
    system_memory_used_bytes,
)

if TYPE_CHECKING:
    from crawler.services.browser_pool import BrowserPool
    from crawler.services.memory_pressure_handler import MemoryPressureHandler

logger = get_logger(__name__)

__all__ = ["MemoryLevel", "MemoryMonitor", "MemoryStatus"]


class MemoryLevel(str, Enum):
    """Memory usage level thresholds."""

    HEALTHY = "healthy"  # <70%
    WARNING = "warning"  # 70-85%
    CRITICAL = "critical"  # 85-95%
    DANGER = "danger"  # >95%


@dataclass
class MemoryStatus:
    """Memory status snapshot."""

    timestamp: datetime
    system_percent: float
    system_used_bytes: int
    system_available_bytes: int
    level: MemoryLevel
    browser_memory: dict[int, int]  # browser_index -> memory_bytes


class MemoryMonitor:
    """Monitors system and browser memory usage with threshold-based alerting.

    Features:
    - System-wide memory tracking
    - Per-browser process memory monitoring
    - Configurable threshold levels (healthy, warning, critical, danger)
    - Periodic checks (default: 30 seconds)
    - Prometheus metrics integration
    - Alert emission on threshold crossings

    Usage:
        monitor = MemoryMonitor(browser_pool=pool, check_interval=30.0)
        await monitor.start()
        # ... monitor runs in background ...
        await monitor.stop()
    """

    def __init__(
        self,
        browser_pool: BrowserPool | None = None,
        pressure_handler: MemoryPressureHandler | None = None,
        check_interval: float = 30.0,
        healthy_threshold: float = 70.0,
        warning_threshold: float = 85.0,
        critical_threshold: float = 95.0,
    ):
        """Initialize memory monitor.

        Args:
            browser_pool: Optional browser pool to monitor browser processes
            pressure_handler: Optional pressure handler for automatic mitigation
            check_interval: Interval in seconds between memory checks (default: 30)
            healthy_threshold: Threshold percentage for healthy level (default: 70)
            warning_threshold: Threshold percentage for warning level (default: 85)
            critical_threshold: Threshold percentage for critical level (default: 95)
        """
        self.browser_pool = browser_pool
        self.pressure_handler = pressure_handler
        self.check_interval = check_interval
        self.healthy_threshold = healthy_threshold
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

        self._monitor_task: asyncio.Task[None] | None = None
        self._running = False
        self._last_level = MemoryLevel.HEALTHY

    async def start(self) -> None:
        """Start the memory monitoring background task.

        Raises:
            RuntimeError: If monitor is already running
        """
        # Guard: already running
        if self._running:
            logger.warning("memory_monitor_already_running")
            return

        logger.info(
            "memory_monitor_starting",
            check_interval=self.check_interval,
            healthy_threshold=self.healthy_threshold,
            warning_threshold=self.warning_threshold,
            critical_threshold=self.critical_threshold,
        )

        self._running = True
        self._monitor_task = asyncio.create_task(self._monitor_loop())

    async def stop(self) -> None:
        """Stop the memory monitoring background task."""
        # Guard: not running
        if not self._running:
            logger.warning("memory_monitor_not_running")
            return

        logger.info("memory_monitor_stopping")
        self._running = False

        # Cancel monitor task
        if self._monitor_task is not None:
            self._monitor_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._monitor_task

        logger.info("memory_monitor_stopped")

    async def _monitor_loop(self) -> None:
        """Background task that runs periodic memory checks."""
        logger.info("memory_monitor_loop_started", interval=self.check_interval)

        while self._running:
            try:
                await self.check_memory()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error("memory_monitor_loop_error", error=str(e))
                # Continue monitoring even if one check fails
                await asyncio.sleep(self.check_interval)

        logger.info("memory_monitor_loop_stopped")

    async def check_memory(self) -> MemoryStatus:
        """Check system and browser memory usage.

        Returns:
            MemoryStatus snapshot with current memory state
        """
        # Get system memory
        vm = psutil.virtual_memory()
        memory_percent = vm.percent
        memory_used = vm.used
        memory_available = vm.available

        # Determine memory level
        level = self._get_memory_level(memory_percent)

        # Check for level transitions and emit alerts
        if level != self._last_level:
            self._emit_alert(level, memory_percent, "system")
            self._last_level = level

        # Update system memory metrics
        system_memory_usage_percent.set(memory_percent)
        system_memory_used_bytes.set(memory_used)
        system_memory_available_bytes.set(memory_available)

        # Track per-browser memory
        browser_memory: dict[int, int] = {}
        if self.browser_pool is not None:
            browser_memory = await self._check_browser_memory()

        status = MemoryStatus(
            timestamp=datetime.now(UTC),
            system_percent=memory_percent,
            system_used_bytes=memory_used,
            system_available_bytes=memory_available,
            level=level,
            browser_memory=browser_memory,
        )

        logger.info(
            "memory_check_completed",
            system_percent=memory_percent,
            level=level.value,
            browser_count=len(browser_memory),
        )

        # Trigger pressure handler if configured
        if self.pressure_handler is not None:
            try:
                actions = await self.pressure_handler.handle_memory_status(status)
                if actions:
                    logger.info(
                        "memory_pressure_actions_taken",
                        action_count=len(actions),
                        actions=[a.action.value for a in actions],
                    )
            except Exception as e:
                logger.error("memory_pressure_handler_error", error=str(e))

        return status

    async def _check_browser_memory(self) -> dict[int, int]:
        """Check memory usage for each browser process.

        Returns:
            Dict mapping browser index to memory usage in bytes
        """
        # Guard: browser pool not initialized
        if self.browser_pool is None or not self.browser_pool.is_initialized():
            return {}

        browser_memory: dict[int, int] = {}

        # Get browser instances (snapshot to avoid holding lock during psutil calls)
        browser_snapshot = await self.browser_pool.get_browser_snapshot()

        # Check memory for each browser
        for browser_index, browser_instance in browser_snapshot:
            try:
                # Try to get PID from browser (Playwright browsers expose this)
                pid = self._get_browser_pid(browser_instance)

                # Guard: no PID available
                if pid is None:
                    continue

                # Get process memory info
                process = psutil.Process(pid)
                memory_info = process.memory_info()
                memory_bytes = memory_info.rss  # Resident Set Size (physical memory)

                browser_memory[browser_index] = memory_bytes

                # Update browser memory metric
                browser_memory_usage_bytes.labels(browser_index=str(browser_index)).set(
                    memory_bytes
                )

                logger.debug(
                    "browser_memory_checked",
                    browser_index=browser_index,
                    memory_mb=memory_bytes / 1024 / 1024,
                    pid=pid,
                )

            except (psutil.NoSuchProcess, psutil.AccessDenied, AttributeError) as e:
                logger.debug(
                    "browser_memory_check_failed",
                    browser_index=browser_index,
                    error=str(e),
                )
                continue

        return browser_memory

    def _get_browser_pid(self, browser_instance: Any) -> int | None:
        """Get PID for a browser instance.

        Args:
            browser_instance: Browser instance to get PID from

        Returns:
            PID if available, None otherwise
        """
        try:
            # Try Playwright's internal _impl_obj (works for chromium/firefox/webkit)
            if hasattr(browser_instance.browser, "_impl_obj"):
                impl = browser_instance.browser._impl_obj
                if hasattr(impl, "_connection"):
                    connection = impl._connection
                    # Try to get process from connection
                    if hasattr(connection, "_transport"):
                        transport = connection._transport
                        if hasattr(transport, "_proc") and transport._proc is not None:
                            pid = transport._proc.pid
                            # Type guard: ensure pid is int
                            return int(pid) if pid is not None else None

            return None

        except Exception as e:
            logger.debug("browser_pid_extraction_failed", error=str(e))
            return None

    def _get_memory_level(self, percent: float) -> MemoryLevel:
        """Get memory level based on usage percentage.

        Args:
            percent: Memory usage percentage (0-100)

        Returns:
            MemoryLevel corresponding to the usage percentage
        """
        if percent >= self.critical_threshold:
            return MemoryLevel.DANGER
        elif percent >= self.warning_threshold:
            return MemoryLevel.CRITICAL
        elif percent >= self.healthy_threshold:
            return MemoryLevel.WARNING
        else:
            return MemoryLevel.HEALTHY

    def _emit_alert(self, level: MemoryLevel, percent: float, alert_type: str) -> None:
        """Emit memory alert.

        Args:
            level: Memory level that triggered the alert
            percent: Current memory usage percentage
            alert_type: Type of alert (system or browser)
        """
        memory_alerts_total.labels(level=level.value, type=alert_type).inc()

        logger.warning(
            "memory_alert",
            level=level.value,
            percent=percent,
            type=alert_type,
            previous_level=self._last_level.value,
        )

    def get_current_level(self) -> MemoryLevel:
        """Get current memory level.

        Returns:
            Current memory level (HEALTHY, WARNING, CRITICAL, or DANGER)
        """
        return self._last_level

    def get_status(self) -> dict[str, Any]:
        """Get current monitor status.

        Returns:
            Dict with monitor status information
        """
        return {
            "running": self._running,
            "check_interval": self.check_interval,
            "healthy_threshold": self.healthy_threshold,
            "warning_threshold": self.warning_threshold,
            "critical_threshold": self.critical_threshold,
            "last_level": self._last_level.value,
        }
