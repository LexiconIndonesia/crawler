"""DLQ service with business logic for dead letter queue operations."""

from crawler.api.generated import (
    DLQCategoryStats,
    DLQEntriesResponse,
    DLQEntry,
    DLQEntryResponse,
    DLQRetryResponse,
    DLQStatsResponse,
    ErrorCategoryEnum,
    JobTypeEnum,
)
from crawler.core.logging import get_logger
from crawler.db.generated.models import ErrorCategoryEnum as DBErrorCategoryEnum
from crawler.db.generated.models import JobTypeEnum as DBJobTypeEnum
from crawler.db.repositories import CrawlJobRepository, DeadLetterQueueRepository

logger = get_logger(__name__)


class DLQService:
    """Service for Dead Letter Queue operations with dependency injection."""

    def __init__(
        self,
        dlq_repo: DeadLetterQueueRepository,
        crawl_job_repo: CrawlJobRepository,
    ):
        """Initialize service with dependencies.

        Args:
            dlq_repo: Dead letter queue repository
            crawl_job_repo: Crawl job repository (for job validation/creation)
        """
        self.dlq_repo = dlq_repo
        self.crawl_job_repo = crawl_job_repo

    async def list_entries(
        self,
        error_category: ErrorCategoryEnum | None = None,
        website_id: str | None = None,
        unresolved_only: bool | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> DLQEntriesResponse:
        """List DLQ entries with filtering and pagination.

        Args:
            error_category: Optional filter by error category
            website_id: Optional filter by website
            unresolved_only: Optional filter by resolved status
            limit: Number of entries per page (max 500)
            offset: Offset for pagination

        Returns:
            Paginated DLQ entries response

        Raises:
            ValueError: If parameters are invalid
            RuntimeError: If retrieval fails
        """
        # Guard: Validate limit
        if limit > 500:
            raise ValueError("Limit cannot exceed 500")

        logger.info(
            "listing_dlq_entries",
            error_category=error_category.value if error_category else None,
            website_id=website_id,
            unresolved_only=unresolved_only,
            limit=limit,
            offset=offset,
        )

        # Convert API enum to DB enum if provided (values are now identical)
        db_error_category = DBErrorCategoryEnum(error_category.value) if error_category else None

        try:
            # Get entries and count in parallel
            entries = await self.dlq_repo.list_entries(
                error_category=db_error_category,
                website_id=website_id,
                unresolved_only=unresolved_only,
                limit=limit,
                offset=offset,
            )

            total = await self.dlq_repo.count_entries(
                error_category=db_error_category,
                website_id=website_id,
                unresolved_only=unresolved_only,
            )

            # Convert DB models to API models
            api_entries = [self._db_entry_to_api(entry) for entry in entries]

            logger.info(
                "dlq_entries_listed",
                entry_count=len(api_entries),
                total=total,
                limit=limit,
                offset=offset,
            )

            return DLQEntriesResponse(
                entries=api_entries,
                total=total,
                limit=limit,
                offset=offset,
            )

        except Exception as e:
            logger.error(
                "dlq_list_failed",
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError("Failed to list DLQ entries") from e

    async def get_entry(self, dlq_id: int) -> DLQEntryResponse:
        """Get a specific DLQ entry by ID.

        Args:
            dlq_id: DLQ entry ID

        Returns:
            DLQ entry response

        Raises:
            ValueError: If entry not found
            RuntimeError: If retrieval fails
        """
        logger.info("getting_dlq_entry", dlq_id=dlq_id)

        try:
            entry = await self.dlq_repo.get_by_id(dlq_id)

            # Guard: Entry not found
            if not entry:
                logger.warning("dlq_entry_not_found", dlq_id=dlq_id)
                raise ValueError(f"DLQ entry with ID {dlq_id} not found")

            logger.info("dlq_entry_retrieved", dlq_id=dlq_id)

            return DLQEntryResponse(entry=self._db_entry_to_api(entry))

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "dlq_get_failed",
                dlq_id=dlq_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Failed to retrieve DLQ entry {dlq_id}") from e

    async def retry_entry(self, dlq_id: int) -> DLQRetryResponse:
        """Manually retry a DLQ entry by creating a new job.

        Args:
            dlq_id: DLQ entry ID to retry

        Returns:
            Retry response with new job ID

        Raises:
            ValueError: If entry not found or already resolved
            RuntimeError: If retry fails
        """
        logger.info("retrying_dlq_entry", dlq_id=dlq_id)

        try:
            entry = await self.dlq_repo.get_by_id(dlq_id)

            # Guard: Entry not found
            if not entry:
                logger.warning("dlq_entry_not_found", dlq_id=dlq_id)
                raise ValueError(f"DLQ entry with ID {dlq_id} not found")

            # Guard: Entry already resolved
            if entry.resolved_at:
                logger.warning("dlq_entry_already_resolved", dlq_id=dlq_id)
                raise ValueError(f"DLQ entry {dlq_id} is already resolved")

            # Create new job - use template-based if website_id exists, else inline
            if entry.website_id:
                # Template-based job using website configuration
                new_job = await self.crawl_job_repo.create_template_based_job(
                    website_id=str(entry.website_id),
                    seed_url=entry.seed_url,
                    job_type=DBJobTypeEnum.ONE_TIME,  # Always one-time for manual retry
                    priority=entry.priority,
                    max_retries=3,  # Reset retry count
                )
            else:
                # Inline job (need minimal config)
                new_job = await self.crawl_job_repo.create_seed_url_submission(
                    seed_url=entry.seed_url,
                    inline_config={"steps": [{"name": "retry", "type": "crawl"}]},
                    job_type=DBJobTypeEnum.ONE_TIME,
                    priority=entry.priority,
                    max_retries=3,
                )

            # Guard: Job creation failed
            if not new_job:
                raise RuntimeError(f"Failed to create retry job for DLQ entry {dlq_id}")

            # Mark DLQ entry as retry attempted (job created successfully)
            await self.dlq_repo.mark_retry_attempted(dlq_id=dlq_id, success=True)

            logger.info(
                "dlq_entry_retried",
                dlq_id=dlq_id,
                new_job_id=str(new_job.id),
            )

            # Emit retry metrics
            from crawler.core import metrics

            metrics.dlq_retry_attempts_total.labels(success="true").inc()

            return DLQRetryResponse(
                job_id=new_job.id,
                dlq_entry_id=dlq_id,
                message="Job retry initiated successfully",
            )

        except ValueError:
            raise
        except Exception as e:
            # Emit failed retry metric
            from crawler.core import metrics

            metrics.dlq_retry_attempts_total.labels(success="false").inc()

            logger.error(
                "dlq_retry_failed",
                dlq_id=dlq_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Failed to retry DLQ entry {dlq_id}") from e

    async def resolve_entry(
        self, dlq_id: int, resolution_notes: str | None = None
    ) -> DLQEntryResponse:
        """Mark a DLQ entry as resolved.

        Args:
            dlq_id: DLQ entry ID to resolve
            resolution_notes: Optional notes explaining resolution

        Returns:
            Updated DLQ entry response

        Raises:
            ValueError: If entry not found or already resolved
            RuntimeError: If resolution fails
        """
        logger.info(
            "resolving_dlq_entry",
            dlq_id=dlq_id,
            has_notes=resolution_notes is not None,
        )

        try:
            entry = await self.dlq_repo.get_by_id(dlq_id)

            # Guard: Entry not found
            if not entry:
                logger.warning("dlq_entry_not_found", dlq_id=dlq_id)
                raise ValueError(f"DLQ entry with ID {dlq_id} not found")

            # Guard: Entry already resolved
            if entry.resolved_at:
                logger.warning("dlq_entry_already_resolved", dlq_id=dlq_id)
                raise ValueError(f"DLQ entry {dlq_id} is already resolved")

            # Mark as resolved
            updated_entry = await self.dlq_repo.mark_resolved(
                dlq_id=dlq_id,
                resolution_notes=resolution_notes,
            )

            # Guard: Update failed
            if not updated_entry:
                raise RuntimeError(f"Failed to update DLQ entry {dlq_id}")

            logger.info("dlq_entry_resolved", dlq_id=dlq_id)

            # Emit resolution metric
            from crawler.core import metrics

            metrics.dlq_resolutions_total.inc()

            return DLQEntryResponse(entry=self._db_entry_to_api(updated_entry))

        except ValueError:
            raise
        except Exception as e:
            logger.error(
                "dlq_resolve_failed",
                dlq_id=dlq_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Failed to resolve DLQ entry {dlq_id}") from e

    async def get_stats(self) -> DLQStatsResponse:
        """Get overall DLQ statistics.

        Returns:
            Statistics including total, unresolved, retry attempts, and by category

        Raises:
            RuntimeError: If stats retrieval fails
        """
        logger.info("getting_dlq_stats")

        try:
            # Get overall stats
            stats = await self.dlq_repo.get_stats()

            # Get stats by category
            category_stats_list = await self.dlq_repo.get_stats_by_category()

            # Convert to API models (values are now identical, just use value)
            by_category = [
                DLQCategoryStats(
                    error_category=ErrorCategoryEnum(cat_stat.error_category.value),
                    total=cat_stat.entry_count,
                    unresolved=cat_stat.unresolved_count,
                )
                for cat_stat in category_stats_list
            ]

            logger.info(
                "dlq_stats_retrieved",
                total_entries=stats.total_entries,
                unresolved=stats.unresolved_count,
            )

            return DLQStatsResponse(
                total_entries=stats.total_entries or 0,
                unresolved_entries=stats.unresolved_count or 0,
                retry_attempts=stats.retry_attempted_count or 0,
                retry_successes=stats.retry_success_count or 0,
                by_category=by_category,
            )

        except Exception as e:
            logger.error(
                "dlq_stats_failed",
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError("Failed to retrieve DLQ statistics") from e

    def _db_entry_to_api(self, db_entry) -> DLQEntry:  # type: ignore[no-untyped-def]
        """Convert database DLQ entry model to API model.

        Args:
            db_entry: Database DLQ entry model

        Returns:
            API DLQ entry model
        """
        return DLQEntry(
            id=db_entry.id,
            job_id=db_entry.job_id,
            seed_url=db_entry.seed_url,
            website_id=db_entry.website_id,
            job_type=JobTypeEnum(db_entry.job_type.value),
            priority=db_entry.priority,
            error_category=ErrorCategoryEnum(db_entry.error_category.value),
            error_message=db_entry.error_message,
            stack_trace=db_entry.stack_trace,
            http_status=db_entry.http_status,
            total_attempts=db_entry.total_attempts,
            first_attempt_at=db_entry.first_attempt_at,
            last_attempt_at=db_entry.last_attempt_at,
            added_to_dlq_at=db_entry.added_to_dlq_at,
            retry_attempted=db_entry.retry_attempted,
            retry_attempted_at=db_entry.retry_attempted_at,
            retry_success=db_entry.retry_success,
            resolved_at=db_entry.resolved_at,
            resolution_notes=db_entry.resolution_notes,
        )
