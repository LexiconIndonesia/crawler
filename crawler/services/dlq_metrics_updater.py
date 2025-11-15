"""Background task to update DLQ gauge metrics periodically."""

import asyncio
from datetime import UTC, datetime

from crawler.core import metrics
from crawler.core.logging import get_logger
from crawler.db.generated.models import ErrorCategoryEnum
from crawler.db.repositories import DeadLetterQueueRepository
from crawler.db.session import get_db

logger = get_logger(__name__)

_metrics_task: asyncio.Task | None = None


async def update_dlq_metrics() -> None:
    """Update DLQ gauge metrics from database.

    This function updates:
    - dlq_entries_unresolved: Current count of unresolved entries
    - dlq_entries_by_category: Count by error category
    - dlq_oldest_unresolved_age_seconds: Age of oldest unresolved entry
    """
    try:
        # Get database session
        async for session in get_db():
            conn = await session.connection()
            dlq_repo = DeadLetterQueueRepository(conn)

            # Get overall stats
            stats = await dlq_repo.get_stats()
            if stats:
                # Update unresolved count
                metrics.dlq_entries_unresolved.set(stats.unresolved_count)
                logger.debug("dlq_metrics_updated", unresolved_count=stats.unresolved_count)
            else:
                # No stats available, reset to 0
                metrics.dlq_entries_unresolved.set(0)

            # Get stats by category
            stats_by_category = await dlq_repo.get_stats_by_category()

            # Build a dict of category counts for efficient lookup
            category_counts = {
                category_stat.error_category: category_stat.entry_count
                for category_stat in stats_by_category
            }

            # Update all error categories (set missing ones to 0)
            for error_category in ErrorCategoryEnum:
                count = category_counts.get(error_category, 0)
                metrics.dlq_entries_by_category.labels(error_category=error_category.value).set(
                    count
                )

            # Get oldest unresolved entry
            oldest_entries = await dlq_repo.get_oldest_unresolved(limit=1)
            if oldest_entries:
                oldest_entry = oldest_entries[0]
                age_seconds = (datetime.now(UTC) - oldest_entry.added_to_dlq_at).total_seconds()
                metrics.dlq_oldest_unresolved_age_seconds.set(age_seconds)
                logger.debug("dlq_oldest_entry_age", age_seconds=age_seconds)
            else:
                # No unresolved entries
                metrics.dlq_oldest_unresolved_age_seconds.set(0)

            # Break after processing with one session
            break

    except asyncio.CancelledError:
        logger.info("dlq_metrics_update_cancelled")
        raise
    except Exception as e:
        logger.error("dlq_metrics_update_failed", error=str(e), exc_info=True)


async def dlq_metrics_updater_loop(interval_seconds: int = 60) -> None:
    """Background loop to periodically update DLQ metrics.

    Args:
        interval_seconds: Update interval in seconds (default: 60)
    """
    logger.info("dlq_metrics_updater_started", interval_seconds=interval_seconds)

    while True:
        try:
            await update_dlq_metrics()
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            logger.info("dlq_metrics_updater_cancelled")
            break
        except Exception as e:
            logger.error("dlq_metrics_updater_error", error=str(e), exc_info=True)
            await asyncio.sleep(interval_seconds)  # Continue after error


async def start_dlq_metrics_updater(interval_seconds: int = 60) -> None:
    """Start the DLQ metrics updater background task.

    Args:
        interval_seconds: Update interval in seconds (default: 60)
    """
    global _metrics_task

    if _metrics_task is not None and not _metrics_task.done():
        logger.warning("dlq_metrics_updater_already_running")
        return

    _metrics_task = asyncio.create_task(dlq_metrics_updater_loop(interval_seconds))
    logger.info("dlq_metrics_updater_task_created")


async def stop_dlq_metrics_updater() -> None:
    """Stop the DLQ metrics updater background task."""
    global _metrics_task

    if _metrics_task is None:
        logger.warning("dlq_metrics_updater_not_running")
        return

    _metrics_task.cancel()
    try:
        await _metrics_task
    except asyncio.CancelledError:
        pass

    _metrics_task = None
    logger.info("dlq_metrics_updater_stopped")
