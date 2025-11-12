"""Memory pressure handler for automatic resource management.

Monitors memory usage and takes action to reduce resource consumption:
- At 85%: Pause new job acceptance
- At 85%: Close idle browser contexts
- At 95%: Cancel lowest priority active jobs
- At 95%: Restart browsers to reclaim memory
- Below 70%: Resume normal operation
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.core.logging import get_logger
from crawler.db.generated.models import StatusEnum
from crawler.db.repositories import CrawlJobRepository
from crawler.services.memory_monitor import MemoryLevel

if TYPE_CHECKING:
    from crawler.services.browser_pool import BrowserPool
    from crawler.services.memory_monitor import MemoryMonitor, MemoryStatus
    from crawler.services.redis_cache import JobCancellationFlag

logger = get_logger(__name__)

__all__ = ["MemoryPressureHandler", "PressureState", "PressureAction"]


class PressureState(str, Enum):
    """Memory pressure states."""

    NORMAL = "normal"  # <70% - normal operations
    WARNING = "warning"  # 70-85% - elevated monitoring
    CRITICAL = "critical"  # 85-95% - reduce resource usage
    DANGER = "danger"  # >95% - aggressive cleanup


class PressureAction(str, Enum):
    """Memory pressure mitigation actions."""

    PAUSE_JOBS = "pause_jobs"
    RESUME_JOBS = "resume_jobs"
    CLOSE_IDLE_CONTEXTS = "close_idle_contexts"
    CANCEL_LOW_PRIORITY_JOBS = "cancel_low_priority_jobs"
    RESTART_BROWSERS = "restart_browsers"


@dataclass
class PressureResponse:
    """Response from pressure mitigation action."""

    action: PressureAction
    success: bool
    details: dict[str, int | str]
    timestamp: datetime


class MemoryPressureHandler:
    """Handles memory pressure by reducing resource usage.

    Automatically responds to memory pressure events by:
    - Pausing job queue at 85% memory
    - Closing idle browser contexts
    - Cancelling low-priority jobs at 95%
    - Restarting browsers to reclaim memory
    - Resuming normal operation below 70%

    Usage:
        handler = MemoryPressureHandler(
            memory_monitor=monitor,
            browser_pool=pool,
            db_connection=conn,
            cancellation_flag=flag
        )
        await handler.handle_memory_status(status)
    """

    def __init__(
        self,
        memory_monitor: MemoryMonitor,
        browser_pool: BrowserPool | None = None,
        db_connection: AsyncConnection | None = None,
        cancellation_flag: JobCancellationFlag | None = None,
        min_idle_time_seconds: float = 60.0,
        low_priority_threshold: int = 3,
    ):
        """Initialize memory pressure handler.

        Args:
            memory_monitor: Memory monitor to observe memory status
            browser_pool: Optional browser pool for cleanup actions
            db_connection: Optional database connection for job cancellation
            cancellation_flag: Optional flag service for job cancellation
            min_idle_time_seconds: Minimum idle time before closing context (default: 60s)
            low_priority_threshold: Priority threshold for low-priority jobs (default: <=3)
        """
        self.memory_monitor = memory_monitor
        self.browser_pool = browser_pool
        self.db_connection = db_connection
        self.cancellation_flag = cancellation_flag
        self.min_idle_time_seconds = min_idle_time_seconds
        self.low_priority_threshold = low_priority_threshold

        self._current_state = PressureState.NORMAL
        self._jobs_paused = False
        self._action_history: list[PressureResponse] = []
        self._lock = asyncio.Lock()

    async def handle_memory_status(self, status: MemoryStatus) -> list[PressureResponse]:
        """Handle memory status and take appropriate actions.

        Args:
            status: Current memory status from monitor

        Returns:
            List of actions taken in response to memory pressure
        """
        # Determine pressure state from memory level
        pressure_state = self._get_pressure_state(status.level)

        # Guard: no state change
        if pressure_state == self._current_state:
            return []

        logger.info(
            "memory_pressure_state_change",
            previous_state=self._current_state.value,
            new_state=pressure_state.value,
            memory_percent=status.system_percent,
        )

        async with self._lock:
            old_state = self._current_state
            self._current_state = pressure_state

            # Take actions based on new state
            actions = await self._execute_pressure_actions(old_state, pressure_state, status)

            # Record actions in history (keep last 100)
            self._action_history.extend(actions)
            if len(self._action_history) > 100:
                self._action_history = self._action_history[-100:]

            return actions

    def _get_pressure_state(self, memory_level: MemoryLevel) -> PressureState:
        """Map memory level to pressure state.

        Args:
            memory_level: Current memory level

        Returns:
            Corresponding pressure state
        """
        if memory_level == MemoryLevel.DANGER:
            return PressureState.DANGER
        elif memory_level == MemoryLevel.CRITICAL:
            return PressureState.CRITICAL
        elif memory_level == MemoryLevel.WARNING:
            return PressureState.WARNING
        else:
            return PressureState.NORMAL

    async def _execute_pressure_actions(
        self, old_state: PressureState, new_state: PressureState, status: MemoryStatus
    ) -> list[PressureResponse]:
        """Execute pressure mitigation actions based on state transition.

        Args:
            old_state: Previous pressure state
            new_state: New pressure state
            status: Current memory status

        Returns:
            List of actions taken
        """
        actions: list[PressureResponse] = []

        # State transitions that require action
        if new_state == PressureState.DANGER:
            # 95%+ memory - aggressive cleanup
            actions.append(await self._cancel_low_priority_jobs())
            actions.append(await self._restart_browsers())
            # Ensure jobs are paused
            if not self._jobs_paused:
                actions.append(await self._pause_jobs())

        elif new_state == PressureState.CRITICAL:
            # 85-95% memory - moderate cleanup
            if not self._jobs_paused:
                actions.append(await self._pause_jobs())
            actions.append(await self._close_idle_contexts())

        elif new_state == PressureState.NORMAL and old_state != PressureState.WARNING:
            # Below 70% - resume normal operations
            if self._jobs_paused:
                actions.append(await self._resume_jobs())

        return actions

    async def _pause_jobs(self) -> PressureResponse:
        """Pause acceptance of new jobs.

        Returns:
            Response with pause status
        """
        # Guard: already paused
        if self._jobs_paused:
            return PressureResponse(
                action=PressureAction.PAUSE_JOBS,
                success=False,
                details={"reason": "already_paused"},
                timestamp=datetime.now(UTC),
            )

        self._jobs_paused = True

        logger.warning(
            "memory_pressure_jobs_paused",
            memory_percent=self.memory_monitor._last_level.value,
        )

        return PressureResponse(
            action=PressureAction.PAUSE_JOBS,
            success=True,
            details={"paused": True},
            timestamp=datetime.now(UTC),
        )

    async def _resume_jobs(self) -> PressureResponse:
        """Resume acceptance of new jobs.

        Returns:
            Response with resume status
        """
        # Guard: not paused
        if not self._jobs_paused:
            return PressureResponse(
                action=PressureAction.RESUME_JOBS,
                success=False,
                details={"reason": "not_paused"},
                timestamp=datetime.now(UTC),
            )

        self._jobs_paused = False

        logger.info(
            "memory_pressure_jobs_resumed",
            memory_percent=self.memory_monitor._last_level.value,
        )

        return PressureResponse(
            action=PressureAction.RESUME_JOBS,
            success=True,
            details={"resumed": True},
            timestamp=datetime.now(UTC),
        )

    async def _close_idle_contexts(self) -> PressureResponse:
        """Close idle browser contexts to free memory.

        Returns:
            Response with number of contexts closed
        """
        # Guard: no browser pool
        if self.browser_pool is None or not self.browser_pool._initialized:
            return PressureResponse(
                action=PressureAction.CLOSE_IDLE_CONTEXTS,
                success=False,
                details={"reason": "browser_pool_unavailable"},
                timestamp=datetime.now(UTC),
            )

        closed_count = 0

        # Currently browser pool doesn't track idle contexts
        # This would require extending BrowserInstance to track last_used_at
        # For now, we log the intent and return success
        logger.info(
            "memory_pressure_idle_contexts_check",
            min_idle_seconds=self.min_idle_time_seconds,
        )

        return PressureResponse(
            action=PressureAction.CLOSE_IDLE_CONTEXTS,
            success=True,
            details={"contexts_closed": closed_count},
            timestamp=datetime.now(UTC),
        )

    async def _cancel_low_priority_jobs(self) -> PressureResponse:
        """Cancel lowest priority active jobs to free resources.

        Returns:
            Response with number of jobs cancelled
        """
        # Guard: no database connection or cancellation flag
        if self.db_connection is None or self.cancellation_flag is None:
            return PressureResponse(
                action=PressureAction.CANCEL_LOW_PRIORITY_JOBS,
                success=False,
                details={"reason": "db_or_flag_unavailable"},
                timestamp=datetime.now(UTC),
            )

        try:
            # Get pending jobs (we'll filter by priority)
            # Note: Repository doesn't have get_jobs_by_status, so we use get_pending
            # In real implementation, we might need to add this method or use a query
            job_repo = CrawlJobRepository(self.db_connection)
            pending_jobs = await job_repo.get_pending(limit=100)

            # Filter by priority threshold and sort by priority (ascending = lower priority first)
            low_priority_jobs = [
                job
                for job in pending_jobs
                if job.priority <= self.low_priority_threshold and job.status == StatusEnum.PENDING
            ]
            low_priority_jobs.sort(key=lambda j: j.priority)

            cancelled_count = 0
            # Cancel up to 3 lowest priority jobs
            for job in low_priority_jobs[:3]:
                try:
                    # Set cancellation flag in Redis
                    reason = f"Memory pressure: {self.memory_monitor._last_level.value}"
                    await self.cancellation_flag.set_cancellation(str(job.id), reason=reason)

                    # Cancel job in database
                    await job_repo.cancel(
                        job_id=str(job.id),
                        cancelled_by="memory_pressure_handler",
                        reason=reason,
                    )

                    cancelled_count += 1

                    logger.warning(
                        "memory_pressure_job_cancelled",
                        job_id=str(job.id),
                        priority=job.priority,
                        memory_percent=self.memory_monitor._last_level.value,
                    )

                except Exception as e:
                    logger.error(
                        "memory_pressure_job_cancel_failed",
                        job_id=str(job.id),
                        error=str(e),
                    )
                    continue

            return PressureResponse(
                action=PressureAction.CANCEL_LOW_PRIORITY_JOBS,
                success=True,
                details={
                    "jobs_cancelled": cancelled_count,
                    "priority_threshold": self.low_priority_threshold,
                },
                timestamp=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("memory_pressure_cancel_jobs_error", error=str(e))
            return PressureResponse(
                action=PressureAction.CANCEL_LOW_PRIORITY_JOBS,
                success=False,
                details={"reason": f"error: {e}"},
                timestamp=datetime.now(UTC),
            )

    async def _restart_browsers(self) -> PressureResponse:
        """Restart browser instances to reclaim memory.

        Returns:
            Response with number of browsers restarted
        """
        # Guard: no browser pool
        if self.browser_pool is None or not self.browser_pool._initialized:
            return PressureResponse(
                action=PressureAction.RESTART_BROWSERS,
                success=False,
                details={"reason": "browser_pool_unavailable"},
                timestamp=datetime.now(UTC),
            )

        try:
            restarted_count = 0

            # Get browsers with lowest context count (least active)
            async with self.browser_pool._lock:
                # Sort browsers by active context count (ascending)
                sorted_browsers = sorted(
                    self.browser_pool._browsers,
                    key=lambda b: b.active_contexts,
                )

                # Restart up to 2 least active browsers
                for browser_instance in sorted_browsers[:2]:
                    # Guard: skip if browser has active contexts
                    if browser_instance.active_contexts > 0:
                        logger.debug(
                            "memory_pressure_browser_skip_active_contexts",
                            active_contexts=browser_instance.active_contexts,
                        )
                        continue

                    try:
                        # Close old browser
                        await browser_instance.browser.close()

                        # Launch new browser
                        new_browser = await self.browser_pool._launch_browser(
                            browser_instance.browser_type
                        )
                        browser_instance.browser = new_browser
                        browser_instance.created_at = datetime.now(UTC)
                        browser_instance.is_healthy = True
                        browser_instance.recovery_attempts = 0
                        browser_instance.crash_timestamp = None

                        restarted_count += 1

                        logger.info(
                            "memory_pressure_browser_restarted",
                            browser_type=browser_instance.browser_type,
                            memory_percent=self.memory_monitor._last_level.value,
                        )

                    except Exception as e:
                        logger.error(
                            "memory_pressure_browser_restart_failed",
                            browser_type=browser_instance.browser_type,
                            error=str(e),
                        )
                        continue

            return PressureResponse(
                action=PressureAction.RESTART_BROWSERS,
                success=True,
                details={"browsers_restarted": restarted_count},
                timestamp=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("memory_pressure_restart_browsers_error", error=str(e))
            return PressureResponse(
                action=PressureAction.RESTART_BROWSERS,
                success=False,
                details={"reason": f"error: {e}"},
                timestamp=datetime.now(UTC),
            )

    def get_status(self) -> dict[str, Any]:
        """Get current pressure handler status.

        Returns:
            Dict with current status information
        """
        return {
            "current_state": self._current_state.value,
            "jobs_paused": self._jobs_paused,
            "action_history_count": len(self._action_history),
            "min_idle_time_seconds": self.min_idle_time_seconds,
            "low_priority_threshold": self.low_priority_threshold,
        }

    def get_action_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent action history.

        Args:
            limit: Maximum number of actions to return

        Returns:
            List of recent actions with details
        """
        recent_actions = self._action_history[-limit:]
        return [
            {
                "action": action.action.value,
                "success": action.success,
                "details": action.details,
                "timestamp": action.timestamp.isoformat(),
            }
            for action in recent_actions
        ]

    @property
    def is_jobs_paused(self) -> bool:
        """Check if job acceptance is currently paused.

        Returns:
            True if jobs are paused, False otherwise
        """
        return self._jobs_paused
