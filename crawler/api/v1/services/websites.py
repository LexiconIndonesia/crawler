"""Website service with business logic."""

from datetime import UTC, datetime

from pydantic import AnyUrl

from crawler.api.generated import (
    CreateWebsiteRequest,
    ListWebsitesResponse,
    UpdateWebsiteRequest,
    UpdateWebsiteResponse,
    WebsiteResponse,
    WebsiteStatistics,
    WebsiteSummary,
    WebsiteWithStatsResponse,
)
from crawler.api.generated import (
    StatusEnum as ApiStatusEnum,
)
from crawler.api.validators import validate_and_calculate_next_run
from crawler.core.logging import get_logger
from crawler.db.generated.models import JobTypeEnum
from crawler.db.generated.models import StatusEnum as DbStatusEnum
from crawler.db.repositories import (
    CrawlJobRepository,
    ScheduledJobRepository,
    WebsiteConfigHistoryRepository,
    WebsiteRepository,
)

logger = get_logger(__name__)


class WebsiteService:
    """Service for website operations with dependency injection."""

    def __init__(
        self,
        website_repo: WebsiteRepository,
        scheduled_job_repo: ScheduledJobRepository,
        config_history_repo: WebsiteConfigHistoryRepository,
        crawl_job_repo: CrawlJobRepository,
    ):
        """Initialize service with dependencies.

        Args:
            website_repo: Website repository for database access
            scheduled_job_repo: Scheduled job repository for database access
            config_history_repo: Website config history repository for versioning
            crawl_job_repo: Crawl job repository for triggering re-crawls
        """
        self.website_repo = website_repo
        self.scheduled_job_repo = scheduled_job_repo
        self.config_history_repo = config_history_repo
        self.crawl_job_repo = crawl_job_repo

    async def create_website(
        self, request: CreateWebsiteRequest, next_run_time: datetime
    ) -> WebsiteResponse:
        """Create a new website with configuration and scheduling.

        Args:
            request: Website creation request
            next_run_time: Next scheduled run time

        Returns:
            Created website response

        Raises:
            ValueError: If website name already exists
            RuntimeError: If website creation fails
        """
        logger.info("creating_website", website_name=request.name, base_url=request.base_url)

        # Build full configuration dict
        # Use mode='json' to properly serialize enums and URLs to strings
        config = {
            "description": request.description,
            "schedule": request.schedule.model_dump(mode="json"),
            "steps": [step.model_dump(mode="json") for step in request.steps],
            "global_config": request.global_config.model_dump(mode="json"),
            "variables": request.variables,
        }

        # Connection has implicit transaction - will commit on success, rollback on exception
        # Check if website name already exists
        existing = await self.website_repo.get_by_name(request.name)
        if existing:
            logger.warning("duplicate_website_name", website_name=request.name)
            raise ValueError(f"Website with name '{request.name}' already exists")

        # Create website
        # Convert AnyUrl to string for database storage
        website = await self.website_repo.create(
            name=request.name,
            base_url=str(request.base_url),
            config=config,
            cron_schedule=request.schedule.cron or "0 0 1,15 * *",
        )

        if not website:
            logger.error("website_creation_failed", website_name=request.name)
            raise RuntimeError("Failed to create website")

        # Create scheduled job if schedule is enabled
        scheduled_job_id = None
        if request.schedule.enabled:
            # Use default cron schedule if not provided (bi-weekly)
            cron_schedule = request.schedule.cron or "0 0 1,15 * *"
            scheduled_job = await self.scheduled_job_repo.create(
                website_id=website.id,
                cron_schedule=cron_schedule,
                next_run_time=next_run_time,
                is_active=True,
            )

            if scheduled_job:
                scheduled_job_id = scheduled_job.id
                logger.info(
                    "scheduled_job_created",
                    website_id=str(website.id),
                    scheduled_job_id=str(scheduled_job.id),
                    next_run_time=next_run_time.isoformat(),
                )

        logger.info(
            "website_created",
            website_id=str(website.id),
            website_name=website.name,
            has_schedule=scheduled_job_id is not None,
        )

        # Build response - convert database status enum to API status enum
        api_status = ApiStatusEnum(website.status.value)

        return WebsiteResponse(
            id=website.id,
            name=website.name,
            base_url=AnyUrl(website.base_url),
            config=website.config,
            status=api_status,
            cron_schedule=website.cron_schedule,
            created_at=website.created_at,
            updated_at=website.updated_at,
            created_by=website.created_by,
            next_run_time=next_run_time if request.schedule.enabled else None,
            scheduled_job_id=scheduled_job_id,
        )

    async def get_website_by_id(self, website_id: str) -> WebsiteWithStatsResponse:
        """Get website by ID with statistics.

        Args:
            website_id: Website ID

        Returns:
            Website with statistics

        Raises:
            ValueError: If website not found
            RuntimeError: If statistics retrieval fails
        """
        logger.info("get_website_by_id", website_id=website_id)

        # Get website
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Get statistics
        stats_row = await self.website_repo.get_statistics(website_id)
        if not stats_row:
            # No statistics yet (no jobs run) - return zeros
            logger.info("no_statistics_found", website_id=website_id)
            stats = WebsiteStatistics(
                total_jobs=0,
                completed_jobs=0,
                failed_jobs=0,
                cancelled_jobs=0,
                success_rate=0.0,
                total_pages_crawled=0,
                last_crawl_at=None,
            )
        else:
            # Convert database statistics to API model
            stats = WebsiteStatistics(
                total_jobs=stats_row.total_jobs,
                completed_jobs=stats_row.completed_jobs,
                failed_jobs=stats_row.failed_jobs,
                cancelled_jobs=stats_row.cancelled_jobs,
                success_rate=float(stats_row.success_rate) if stats_row.success_rate else 0.0,
                total_pages_crawled=stats_row.total_pages_crawled,
                last_crawl_at=stats_row.last_crawl_at,
            )

        # Get scheduled job info
        scheduled_jobs = await self.scheduled_job_repo.get_by_website_id(website.id)
        scheduled_job_id = None
        next_run_time = None
        if scheduled_jobs:
            # Get the active scheduled job
            active_job = next((job for job in scheduled_jobs if job.is_active), None)
            if active_job:
                scheduled_job_id = active_job.id
                next_run_time = active_job.next_run_time

        # Convert database status to API status
        api_status = ApiStatusEnum(website.status.value)

        # Build response
        return WebsiteWithStatsResponse(
            id=website.id,
            name=website.name,
            base_url=AnyUrl(website.base_url),
            config=website.config,
            status=api_status,
            cron_schedule=website.cron_schedule,
            created_at=website.created_at,
            updated_at=website.updated_at,
            created_by=website.created_by,
            next_run_time=next_run_time,
            scheduled_job_id=scheduled_job_id,
            statistics=stats,
        )

    async def list_websites(
        self, status: str | None = None, limit: int = 20, offset: int = 0
    ) -> ListWebsitesResponse:
        """List websites with pagination and filtering.

        Args:
            status: Optional status filter ('active' or 'inactive')
            limit: Maximum number of results (default: 20, max: 100)
            offset: Number of results to skip (default: 0)

        Returns:
            Paginated list of websites with total count

        Raises:
            ValueError: If invalid status value provided
        """
        logger.info("list_websites", status=status, limit=limit, offset=offset)

        # Convert API status string to database enum if provided
        db_status = None
        if status:
            try:
                db_status = DbStatusEnum(status)
            except ValueError as e:
                logger.warning("invalid_status", status=status)
                raise ValueError(f"Invalid status value: {status}") from e

        # Get websites from repository
        websites = await self.website_repo.list(status=db_status, limit=limit, offset=offset)

        # Get total count
        total = await self.website_repo.count(status=db_status)

        # Convert to summary models
        summaries = [
            WebsiteSummary(
                id=website.id,
                name=website.name,
                base_url=AnyUrl(website.base_url),
                status=ApiStatusEnum(website.status.value),
                cron_schedule=website.cron_schedule,
                created_at=website.created_at,
                updated_at=website.updated_at,
            )
            for website in websites
        ]

        logger.info("websites_listed", count=len(summaries), total=total)

        return ListWebsitesResponse(
            websites=summaries,
            total=total,
            limit=limit,
            offset=offset,
        )

    async def update_website(
        self,
        website_id: str,
        request: UpdateWebsiteRequest,
        changed_by: str | None = None,
    ) -> UpdateWebsiteResponse:
        """Update website configuration with versioning.

        Args:
            website_id: Website ID
            request: Update request with new configuration
            changed_by: User/system making the change

        Returns:
            Updated website with version info

        Raises:
            ValueError: If website not found or no changes detected
            RuntimeError: If update operation fails
        """
        logger.info("update_website", website_id=website_id, has_recrawl=request.trigger_recrawl)

        # Get current website
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Check if there are any changes
        has_changes = False
        new_config = dict(website.config) if website.config else {}

        # Update fields if provided
        update_name = request.name if request.name else website.name
        update_status = DbStatusEnum(request.status.value) if request.status else website.status

        # Update configuration components
        if request.steps:
            new_config["steps"] = [step.model_dump(mode="json") for step in request.steps]
            has_changes = True

        if request.variables is not None:
            new_config["variables"] = request.variables
            has_changes = True

        if request.global_config:
            new_config["global_config"] = request.global_config.model_dump(mode="json")
            has_changes = True

        if request.schedule:
            new_config["schedule"] = request.schedule.model_dump(mode="json")
            has_changes = True

        # Determine cron schedule
        new_cron = website.cron_schedule
        if request.schedule and request.schedule.cron:
            # Validate cron expression
            is_valid, error_or_next_run = validate_and_calculate_next_run(request.schedule.cron)
            if not is_valid:
                logger.warning("invalid_cron", cron=request.schedule.cron, error=error_or_next_run)
                raise ValueError(f"Invalid cron expression: {error_or_next_run}")
            new_cron = request.schedule.cron
            has_changes = True

        # Check if name changed
        if request.name and request.name != website.name:
            # Check for duplicate name
            existing = await self.website_repo.get_by_name(request.name)
            if existing and str(existing.id) != website_id:
                raise ValueError(f"Website with name '{request.name}' already exists")
            has_changes = True

        if not has_changes and not request.status:
            logger.info("no_changes_detected", website_id=website_id)
            raise ValueError("No changes detected in the update request")

        # Save current config to history
        latest_version = await self.config_history_repo.get_latest_version(website_id)
        new_version = latest_version + 1

        await self.config_history_repo.create(
            website_id=website_id,
            version=new_version,
            config=website.config if website.config else {},
            changed_by=changed_by,
            change_reason=request.change_reason,
        )
        logger.info(
            "config_history_saved",
            website_id=website_id,
            version=new_version,
            changed_by=changed_by,
        )

        # Update website
        updated_website = await self.website_repo.update(
            website_id=website_id,
            name=update_name,
            config=new_config,
            cron_schedule=new_cron,
            status=update_status,
        )

        if not updated_website:
            raise RuntimeError("Failed to update website")

        logger.info("website_updated", website_id=website_id, version=new_version)

        # Update scheduled job if schedule changed
        scheduled_job_id = None
        next_run_time = None

        if request.schedule:
            scheduled_jobs = await self.scheduled_job_repo.get_by_website_id(website_id)

            if request.schedule.enabled:
                # Determine effective cron schedule
                effective_cron = new_cron if new_cron else website.cron_schedule
                if not effective_cron:
                    effective_cron = "0 0 1,15 * *"  # Default bi-weekly

                # Calculate next run time
                is_valid, next_run = validate_and_calculate_next_run(effective_cron)
                if isinstance(next_run, datetime):
                    next_run_time = next_run

                # Guard: next_run_time must be set
                if not next_run_time:
                    next_run_time = datetime.now(UTC)

                if scheduled_jobs:
                    # Update existing scheduled job
                    for job in scheduled_jobs:
                        await self.scheduled_job_repo.update(
                            job_id=job.id,
                            cron_schedule=new_cron,
                            next_run_time=next_run_time,
                            is_active=True,
                        )
                        scheduled_job_id = job.id
                        logger.info("scheduled_job_updated", job_id=job.id)
                else:
                    # Create new scheduled job
                    new_job = await self.scheduled_job_repo.create(
                        website_id=website_id,
                        cron_schedule=effective_cron,
                        next_run_time=next_run_time,
                        is_active=True,
                    )
                    if new_job:
                        scheduled_job_id = new_job.id
                        logger.info("scheduled_job_created", job_id=new_job.id)
            else:
                # Disable scheduled jobs
                for job in scheduled_jobs:
                    await self.scheduled_job_repo.toggle_status(job_id=job.id, is_active=False)
                    logger.info("scheduled_job_disabled", job_id=job.id)

        # Trigger re-crawl if requested
        recrawl_job_id = None
        if request.trigger_recrawl:
            # Create a one-time crawl job with updated configuration
            crawl_job = await self.crawl_job_repo.create(
                website_id=website_id,
                seed_url=updated_website.base_url,
                job_type=JobTypeEnum.ONE_TIME,
                priority=5,
                max_retries=3,
            )
            if crawl_job:
                recrawl_job_id = crawl_job.id
                logger.info("recrawl_triggered", job_id=recrawl_job_id, website_id=website_id)

        # Build response
        api_status = ApiStatusEnum(updated_website.status.value)

        return UpdateWebsiteResponse(
            id=updated_website.id,
            name=updated_website.name,
            base_url=AnyUrl(updated_website.base_url),
            config=updated_website.config,
            status=api_status,
            cron_schedule=updated_website.cron_schedule,
            created_at=updated_website.created_at,
            updated_at=updated_website.updated_at,
            created_by=updated_website.created_by,
            next_run_time=next_run_time,
            scheduled_job_id=scheduled_job_id,
            config_version=new_version,
            recrawl_job_id=recrawl_job_id,
        )
