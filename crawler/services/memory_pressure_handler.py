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
from contextlib import aclosing
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from config import Settings
from crawler.cache.session import get_redis
from crawler.core.logging import get_logger
from crawler.db.generated.models import StatusEnum
from crawler.db.repositories import CrawlJobRepository
from crawler.db.session import get_db
from crawler.services.memory_monitor import MemoryLevel
from crawler.services.redis_cache import JobCancellationFlag

if TYPE_CHECKING:
    from crawler.services.browser_pool import BrowserPool
    from crawler.services.memory_monitor import MemoryMonitor, MemoryStatus

logger = get_logger(__name__)

__all__ = ["MemoryPressureHandler", "PressureState", "PressureAction", "PressureResponse"]


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

    Note:
        Database and Redis connections are acquired on-demand via get_db() and
        get_redis() when needed, rather than being held persistently. This avoids
        resource leaks and connection pool exhaustion.

    Usage:
        handler = MemoryPressureHandler(
            memory_monitor=monitor,
            settings=settings,
            browser_pool=pool,
            min_idle_time_seconds=60.0,
            low_priority_threshold=3
        )
        await handler.handle_memory_status(status)
    """

    def __init__(
        self,
        memory_monitor: MemoryMonitor,
        settings: Settings,
        browser_pool: BrowserPool | None = None,
        min_idle_time_seconds: float = 60.0,
        low_priority_threshold: int = 3,
    ):
        """Initialize memory pressure handler.

        Args:
            memory_monitor: Memory monitor to observe memory status
            settings: Application settings for creating connections on-demand
            browser_pool: Optional browser pool for cleanup actions
            min_idle_time_seconds: Minimum idle time before closing context (default: 60s)
            low_priority_threshold: Priority threshold for low-priority jobs (default: <=3)

        Note:
            Database and Redis connections are acquired on-demand rather than held
            persistently to avoid resource leaks and connection pool exhaustion.
        """
        self.memory_monitor = memory_monitor
        self.settings = settings
        self.browser_pool = browser_pool
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

        elif new_state in (PressureState.WARNING, PressureState.NORMAL) and old_state in (
            PressureState.CRITICAL,
            PressureState.DANGER,
        ):
            # Recovering from critical/danger - resume operations
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
            memory_percent=self.memory_monitor.get_current_level().value,
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
            memory_percent=self.memory_monitor.get_current_level().value,
        )

        return PressureResponse(
            action=PressureAction.RESUME_JOBS,
            success=True,
            details={"resumed": True},
            timestamp=datetime.now(UTC),
        )

    async def _close_idle_contexts(self) -> PressureResponse:
        """Close idle browser contexts to free memory.

        Closes contexts that have been idle for longer than min_idle_time_seconds.

        Returns:
            Response with number of contexts closed
        """
        # Guard: no browser pool
        if self.browser_pool is None or not self.browser_pool.is_initialized():
            return PressureResponse(
                action=PressureAction.CLOSE_IDLE_CONTEXTS,
                success=False,
                details={"reason": "browser_pool_unavailable"},
                timestamp=datetime.now(UTC),
            )

        try:
            # Close idle contexts using BrowserPool public API
            closed_count = await self.browser_pool.close_idle_contexts(
                min_idle_seconds=self.min_idle_time_seconds
            )

            logger.info(
                "memory_pressure_idle_contexts_closed",
                closed_count=closed_count,
                min_idle_seconds=self.min_idle_time_seconds,
            )

            return PressureResponse(
                action=PressureAction.CLOSE_IDLE_CONTEXTS,
                success=True,
                details={"contexts_closed": closed_count},
                timestamp=datetime.now(UTC),
            )

        except Exception as e:
            logger.error("memory_pressure_close_idle_contexts_error", error=str(e))
            return PressureResponse(
                action=PressureAction.CLOSE_IDLE_CONTEXTS,
                success=False,
                details={"reason": f"error: {e}"},
                timestamp=datetime.now(UTC),
            )

    async def _cancel_low_priority_jobs(self) -> PressureResponse:
        """Cancel lowest priority active jobs to free resources.

        Acquires database and Redis connections on-demand for the operation.

        Returns:
            Response with number of jobs cancelled
        """
        try:
            cancelled_count = 0

            # Acquire database session on-demand
            async with aclosing(get_db()) as db_iter:
                db_session = await db_iter.__anext__()
                db_connection = await db_session.connection()

                # Get pending jobs
                job_repo = CrawlJobRepository(db_connection)
                pending_jobs = await job_repo.get_pending(limit=100)

                # Filter by priority threshold and sort by priority (lower first)
                low_priority_jobs = [
                    job
                    for job in pending_jobs
                    if job.priority <= self.low_priority_threshold
                    and job.status == StatusEnum.PENDING
                ]
                low_priority_jobs.sort(key=lambda j: j.priority)

                # Acquire Redis client on-demand for cancellation flags
                async with aclosing(get_redis()) as redis_iter:
                    redis_client = await redis_iter.__anext__()
                    cancellation_flag = JobCancellationFlag(
                        redis_client=redis_client, settings=self.settings
                    )

                    # Cancel up to 3 lowest priority jobs
                    for job in low_priority_jobs[:3]:
                        try:
                            # Set cancellation flag in Redis
                            memory_level = self.memory_monitor.get_current_level().value
                            reason = f"Memory pressure: {memory_level}"
                            await cancellation_flag.set_cancellation(str(job.id), reason=reason)

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
                                memory_percent=self.memory_monitor.get_current_level().value,
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
        if self.browser_pool is None or not self.browser_pool.is_initialized():
            return PressureResponse(
                action=PressureAction.RESTART_BROWSERS,
                success=False,
                details={"reason": "browser_pool_unavailable"},
                timestamp=datetime.now(UTC),
            )

        try:
            # Restart up to 2 idle browsers using BrowserPool public API
            restarted_count = await self.browser_pool.restart_idle_browsers(max_count=2)

            logger.info(
                "memory_pressure_browsers_restarted",
                restarted_count=restarted_count,
                memory_percent=self.memory_monitor.get_current_level().value,
            )

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

    def is_jobs_paused(self) -> bool:
        """Check if job acceptance is currently paused.

        Returns:
            True if jobs are paused, False otherwise
        """
        return self._jobs_paused
