"""Log service with business logic for log retrieval."""

from datetime import datetime

from crawler.api.generated import CrawlLogEntry, CrawlLogsResponse, LogLevelEnum
from crawler.core.logging import get_logger
from crawler.db.generated.models import LogLevelEnum as DBLogLevelEnum
from crawler.db.repositories import CrawlJobRepository, CrawlLogRepository

logger = get_logger(__name__)


class LogService:
    """Service for crawl log operations with dependency injection."""

    def __init__(
        self,
        crawl_log_repo: CrawlLogRepository,
        crawl_job_repo: CrawlJobRepository,
    ):
        """Initialize service with dependencies.

        Args:
            crawl_log_repo: Crawl log repository for log access
            crawl_job_repo: Crawl job repository for job validation
        """
        self.crawl_log_repo = crawl_log_repo
        self.crawl_job_repo = crawl_job_repo

    async def get_job_logs(
        self,
        job_id: str,
        log_level: LogLevelEnum | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        search: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> CrawlLogsResponse:
        """Get filtered logs for a crawl job.

        This method:
        1. Validates that the job exists
        2. Retrieves logs from database with filters
        3. Counts total logs matching filters
        4. Returns paginated response

        Args:
            job_id: Job ID
            log_level: Optional log level filter
            start_time: Optional start timestamp filter
            end_time: Optional end timestamp filter
            search: Optional text search in message
            limit: Number of logs per page
            offset: Offset for pagination

        Returns:
            Paginated log response

        Raises:
            ValueError: If job not found
            RuntimeError: If log retrieval fails
        """
        logger.info(
            "retrieving_job_logs",
            job_id=job_id,
            log_level=log_level.value if log_level else None,
            start_time=start_time.isoformat() if start_time else None,
            end_time=end_time.isoformat() if end_time else None,
            search=search,
            limit=limit,
            offset=offset,
        )

        # Guard: Validate job exists
        job = await self.crawl_job_repo.get_by_id(job_id)
        if not job:
            logger.warning("job_not_found", job_id=job_id)
            raise ValueError(f"Job with ID '{job_id}' not found")

        # Convert API log level enum to DB log level enum
        db_log_level = DBLogLevelEnum[log_level.value] if log_level else None

        try:
            # Get filtered logs with pagination
            logs = await self.crawl_log_repo.get_job_logs_filtered(
                job_id=job_id,
                log_level=db_log_level,
                start_time=start_time,
                end_time=end_time,
                search_text=search,
                limit=limit,
                offset=offset,
            )

            # Count total logs matching filters
            total = await self.crawl_log_repo.count_job_logs_filtered(
                job_id=job_id,
                log_level=db_log_level,
                start_time=start_time,
                end_time=end_time,
                search_text=search,
            )

            # Convert DB models to API models
            log_entries = [
                CrawlLogEntry(
                    id=log.id,
                    job_id=log.job_id,
                    website_id=log.website_id,
                    step_name=log.step_name,
                    log_level=LogLevelEnum(log.log_level.value),
                    message=log.message,
                    context=log.context,
                    trace_id=log.trace_id,
                    created_at=log.created_at,
                )
                for log in logs
            ]

            logger.info(
                "job_logs_retrieved",
                job_id=job_id,
                log_count=len(log_entries),
                total=total,
                limit=limit,
                offset=offset,
            )

            return CrawlLogsResponse(
                logs=log_entries,
                total=total,
                limit=limit,
                offset=offset,
            )

        except Exception as e:
            logger.error(
                "log_retrieval_failed",
                job_id=job_id,
                error=str(e),
                exc_info=True,
            )
            raise RuntimeError(f"Failed to retrieve logs for job '{job_id}'") from e
