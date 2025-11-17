"""Website service with business logic."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import AnyUrl

from crawler.api.generated import (
    ConfigHistoryListResponse,
    ConfigHistoryResponse,
    CrawlJobStatus,
    CreateWebsiteRequest,
    DeleteWebsiteResponse,
    ListWebsitesResponse,
    RollbackConfigRequest,
    RollbackConfigResponse,
    ScheduleStatusResponse,
    TriggerCrawlRequest,
    TriggerCrawlResponse,
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
from crawler.services.nats_queue import NATSQueueService
from crawler.services.priority_queue import PRIORITY_MANUAL_TRIGGER

logger = get_logger(__name__)


class WebsiteService:
    """Service for website operations with dependency injection."""

    def __init__(
        self,
        website_repo: WebsiteRepository,
        scheduled_job_repo: ScheduledJobRepository,
        config_history_repo: WebsiteConfigHistoryRepository,
        crawl_job_repo: CrawlJobRepository,
        nats_queue: NATSQueueService,
    ):
        """Initialize service with dependencies.

        Args:
            website_repo: Website repository for database access
            scheduled_job_repo: Scheduled job repository for database access
            config_history_repo: Website config history repository for versioning
            crawl_job_repo: Crawl job repository for triggering re-crawls
            nats_queue: NATS queue service for job queueing
        """
        self.website_repo = website_repo
        self.scheduled_job_repo = scheduled_job_repo
        self.config_history_repo = config_history_repo
        self.crawl_job_repo = crawl_job_repo
        self.nats_queue = nats_queue

    async def create_website(
        self,
        request: CreateWebsiteRequest,
        next_run_time: datetime,
        created_by: str | None = None,
    ) -> WebsiteResponse:
        """Create a new website with configuration and scheduling.

        Args:
            request: Website creation request
            next_run_time: Next scheduled run time
            created_by: User/system making the creation (for audit trail)

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
            created_by=created_by,
        )

        if not website:
            logger.error("website_creation_failed", website_name=request.name)
            raise RuntimeError("Failed to create website")

        # Create scheduled job if schedule is enabled
        scheduled_job_id = None
        if request.schedule.enabled:
            # Use default cron schedule if not provided (bi-weekly)
            cron_schedule = request.schedule.cron or "0 0 1,15 * *"
            timezone = request.schedule.timezone or "UTC"  # Use default if not provided

            scheduled_job = await self.scheduled_job_repo.create(
                website_id=website.id,
                cron_schedule=cron_schedule,
                next_run_time=next_run_time,
                timezone=timezone,
                is_active=True,
            )

            if scheduled_job:
                scheduled_job_id = scheduled_job.id
                logger.info(
                    "scheduled_job_created",
                    website_id=str(website.id),
                    scheduled_job_id=str(scheduled_job.id),
                    cron_schedule=cron_schedule,
                    next_run_time=next_run_time.isoformat(),
                    timezone=timezone,
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
        if request.schedule:
            if request.schedule.cron:
                # Validate cron expression
                is_valid, error_or_next_run = validate_and_calculate_next_run(request.schedule.cron)
                if not is_valid:
                    logger.warning(
                        "invalid_cron", cron=request.schedule.cron, error=error_or_next_run
                    )
                    raise ValueError(f"Invalid cron expression: {error_or_next_run}")
                new_cron = request.schedule.cron
            else:
                # Allow clearing the cron schedule by sending cron: null
                new_cron = None
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
                # Determine effective cron schedule for scheduled jobs
                # Use new_cron if set, otherwise use default
                # Note: new_cron could be None if user cleared it
                effective_cron = new_cron if new_cron else "0 0 1,15 * *"

                # Get timezone from schedule config (use default if not provided)
                timezone = request.schedule.timezone or "UTC"

                # Calculate next run time in user's timezone
                is_valid, next_run = validate_and_calculate_next_run(
                    effective_cron, timezone=timezone
                )
                if not is_valid or not isinstance(next_run, datetime):
                    logger.warning(
                        "invalid_cron_or_timezone",
                        cron=effective_cron,
                        timezone=timezone,
                        error=next_run,
                    )
                    raise ValueError(f"Invalid cron expression or timezone: {next_run}")
                next_run_time = next_run

                if scheduled_jobs:
                    # Update existing scheduled job with effective cron and timezone
                    for job in scheduled_jobs:
                        await self.scheduled_job_repo.update(
                            job_id=job.id,
                            cron_schedule=effective_cron,
                            next_run_time=next_run_time,
                            timezone=timezone,
                            is_active=True,
                        )
                        scheduled_job_id = job.id
                        logger.info(
                            "scheduled_job_updated",
                            job_id=job.id,
                            cron_schedule=effective_cron,
                            next_run_time=next_run_time.isoformat(),
                            timezone=timezone,
                        )
                else:
                    # Create new scheduled job with effective cron and timezone
                    new_job = await self.scheduled_job_repo.create(
                        website_id=website_id,
                        cron_schedule=effective_cron,
                        next_run_time=next_run_time,
                        timezone=timezone,
                        is_active=True,
                    )
                    if new_job:
                        scheduled_job_id = new_job.id
                        logger.info(
                            "scheduled_job_created",
                            job_id=new_job.id,
                            cron_schedule=effective_cron,
                            next_run_time=next_run_time.isoformat(),
                            timezone=timezone,
                        )
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

    async def delete_website(
        self,
        website_id: str,
        delete_data: bool = False,
    ) -> DeleteWebsiteResponse:
        """Delete website with soft delete and job cancellation.

        Args:
            website_id: Website ID
            delete_data: Whether to delete all crawled data (not implemented yet)

        Returns:
            DeleteWebsiteResponse with deletion details

        Raises:
            ValueError: If website not found or already deleted
            RuntimeError: If deletion operation fails
        """
        logger.info("delete_website", website_id=website_id, delete_data=delete_data)

        # Get current website
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Check if already deleted
        if website.deleted_at:
            logger.warning("website_already_deleted", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' is already deleted")

        # Cancel all active jobs for this website
        active_jobs = await self.crawl_job_repo.get_active_by_website(website_id)
        cancelled_job_ids = []

        for job in active_jobs:
            cancelled_job = await self.crawl_job_repo.cancel(
                job_id=job.id,
                cancelled_by="system",
                reason=f"Website {website_id} deleted",
            )
            if cancelled_job:
                cancelled_job_ids.append(str(cancelled_job.id))
                logger.info("job_cancelled", job_id=cancelled_job.id, website_id=website_id)

        # Save configuration to history before deletion
        latest_version = await self.config_history_repo.get_latest_version(website_id)
        new_version = latest_version + 1

        await self.config_history_repo.create(
            website_id=website_id,
            version=new_version,
            config=website.config if website.config else {},
            changed_by="system",
            change_reason="Website deleted - config archived",
        )
        logger.info("config_archived", website_id=website_id, version=new_version)

        # Soft delete the website
        deleted_website = await self.website_repo.soft_delete(website_id)

        if not deleted_website:
            raise RuntimeError("Failed to delete website")

        # Guard: deleted_at must be set after soft delete
        if not deleted_website.deleted_at:
            raise RuntimeError("Soft delete failed: deleted_at not set")

        logger.info(
            "website_deleted",
            website_id=website_id,
            cancelled_jobs=len(cancelled_job_ids),
            config_version=new_version,
        )

        return DeleteWebsiteResponse(
            id=deleted_website.id,
            name=deleted_website.name,
            deleted_at=deleted_website.deleted_at,
            cancelled_jobs=len(cancelled_job_ids),
            cancelled_job_ids=[UUID(job_id) for job_id in cancelled_job_ids],
            config_archived_version=new_version,
            message=f"Website '{deleted_website.name}' deleted successfully",
        )

    async def get_config_history(
        self,
        website_id: str,
        limit: int = 10,
        offset: int = 0,
    ) -> ConfigHistoryListResponse:
        """Get configuration history for a website.

        Args:
            website_id: Website ID
            limit: Maximum number of versions to return
            offset: Number of versions to skip

        Returns:
            Paginated list of configuration versions

        Raises:
            ValueError: If website not found
            RuntimeError: If history retrieval fails
        """
        logger.info("get_config_history", website_id=website_id, limit=limit, offset=offset)

        # Guard: Verify website exists
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Get history entries
        history = await self.config_history_repo.list_history(
            website_id=website_id, limit=limit, offset=offset
        )

        # Get total count
        latest_version = await self.config_history_repo.get_latest_version(website_id)

        # Convert to response models
        versions = [
            ConfigHistoryResponse(
                id=entry.id,
                website_id=entry.website_id,
                version=entry.version,
                config=entry.config,
                changed_by=entry.changed_by,
                change_reason=entry.change_reason,
                created_at=entry.created_at,
            )
            for entry in history
        ]

        logger.info("config_history_retrieved", website_id=website_id, count=len(versions))

        return ConfigHistoryListResponse(
            versions=versions,
            total=latest_version,
            limit=limit,
            offset=offset,
        )

    async def get_config_version(
        self,
        website_id: str,
        version: int,
    ) -> ConfigHistoryResponse:
        """Get a specific configuration version.

        Args:
            website_id: Website ID
            version: Version number

        Returns:
            Configuration version details

        Raises:
            ValueError: If website or version not found
            RuntimeError: If version retrieval fails
        """
        logger.info("get_config_version", website_id=website_id, version=version)

        # Guard: Verify website exists
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Get specific version
        entry = await self.config_history_repo.get_by_version(website_id, version)
        if not entry:
            logger.warning("version_not_found", website_id=website_id, version=version)
            raise ValueError(f"Configuration version {version} not found for website")

        logger.info("config_version_retrieved", website_id=website_id, version=version)

        return ConfigHistoryResponse(
            id=entry.id,
            website_id=entry.website_id,
            version=entry.version,
            config=entry.config,
            changed_by=entry.changed_by,
            change_reason=entry.change_reason,
            created_at=entry.created_at,
        )

    async def rollback_config(
        self,
        website_id: str,
        target_version: int,
        request: RollbackConfigRequest | None,
    ) -> RollbackConfigResponse:
        """Rollback website configuration to a previous version.

        Args:
            website_id: Website ID
            target_version: Version number to rollback to
            request: Optional rollback request with reason and recrawl flag

        Returns:
            Rollback response with updated website and version info

        Raises:
            ValueError: If website or version not found, or invalid rollback
            RuntimeError: If rollback operation fails
        """
        rollback_reason = request.rollback_reason if request else "Configuration rollback"
        trigger_recrawl = request.trigger_recrawl if request else False

        logger.info(
            "rollback_config",
            website_id=website_id,
            target_version=target_version,
            trigger_recrawl=trigger_recrawl,
        )

        # Guard: Verify website exists
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Guard: Get target version configuration
        target_config_entry = await self.config_history_repo.get_by_version(
            website_id, target_version
        )
        if not target_config_entry:
            logger.warning(
                "target_version_not_found", website_id=website_id, target_version=target_version
            )
            raise ValueError(f"Configuration version {target_version} not found")

        # Save current configuration to history before rollback
        current_version = await self.config_history_repo.get_latest_version(website_id)

        # Guard: Prevent rollback to current version (no-op that creates unnecessary history)
        if target_version == current_version:
            logger.warning(
                "rollback_to_current_version_attempted",
                website_id=website_id,
                current_version=current_version,
                target_version=target_version,
            )
            raise ValueError("Cannot rollback to the current version")

        new_version = current_version + 1

        await self.config_history_repo.create(
            website_id=website_id,
            version=new_version,
            config=website.config if website.config else {},
            changed_by="system",
            change_reason=(
                f"Pre-rollback snapshot (rolling back from v{current_version} to "
                f"v{target_version}): {rollback_reason}"
            ),
        )

        logger.info(
            "pre_rollback_snapshot_saved",
            website_id=website_id,
            version=new_version,
            target_version=target_version,
        )

        # Restore configuration from target version
        rollback_version = new_version + 1
        await self.config_history_repo.create(
            website_id=website_id,
            version=rollback_version,
            config=target_config_entry.config,
            changed_by="system",
            change_reason=f"Rolled back to version {target_version}: {rollback_reason}",
        )

        # Update website with restored configuration
        # Extract cron_schedule from target config to maintain data integrity
        target_config = target_config_entry.config or {}
        target_schedule = target_config.get("schedule", {})
        target_cron = target_schedule.get("cron")

        updated_website = await self.website_repo.update(
            website_id=website_id,
            name=website.name,
            config=target_config,
            cron_schedule=target_cron,  # Use cron from restored config
            status=website.status,
        )

        if not updated_website:
            raise RuntimeError("Failed to update website during rollback")

        logger.info(
            "config_rolled_back",
            website_id=website_id,
            from_version=current_version,
            to_version=target_version,
            new_version=rollback_version,
        )

        # Update scheduled job with restored cron_schedule
        scheduled_jobs = await self.scheduled_job_repo.get_by_website_id(website_id)
        scheduled_job_id = None
        next_run_time = None

        if scheduled_jobs and target_cron:
            # Determine timezone (prefer restored config, then existing job, then UTC)
            target_timezone = None
            if isinstance(target_schedule, dict):
                target_timezone = target_schedule.get("timezone")
            job_timezone = target_timezone or getattr(scheduled_jobs[0], "timezone", None) or "UTC"

            # Calculate next run time from restored cron schedule in the correct timezone
            is_valid, result = validate_and_calculate_next_run(target_cron, timezone=job_timezone)
            if is_valid and isinstance(result, datetime):
                next_run_time = result
            else:
                # Fallback to current time if cron validation fails
                next_run_time = datetime.now(UTC)

            # Update all scheduled jobs with restored cron_schedule
            for job in scheduled_jobs:
                await self.scheduled_job_repo.update(
                    job_id=job.id,
                    cron_schedule=target_cron,
                    next_run_time=next_run_time,
                    is_active=job.is_active,  # Preserve active status
                    timezone=job_timezone,
                )
                if job.is_active:
                    scheduled_job_id = job.id

            logger.info(
                "scheduled_jobs_updated_after_rollback",
                website_id=website_id,
                cron_schedule=target_cron,
                next_run_time=next_run_time.isoformat() if next_run_time else None,
                timezone=job_timezone,
            )
        elif scheduled_jobs:
            # No target_cron, just get existing job info
            active_job = next((job for job in scheduled_jobs if job.is_active), None)
            if active_job:
                scheduled_job_id = active_job.id
                next_run_time = active_job.next_run_time

        # Trigger re-crawl if requested
        recrawl_job_id = None
        if trigger_recrawl:
            crawl_job = await self.crawl_job_repo.create(
                website_id=website_id,
                seed_url=updated_website.base_url,
                job_type=JobTypeEnum.ONE_TIME,
                priority=5,
                max_retries=3,
            )
            if crawl_job:
                recrawl_job_id = crawl_job.id
                logger.info(
                    "recrawl_triggered_after_rollback",
                    job_id=recrawl_job_id,
                    website_id=website_id,
                )

        # Build response
        api_status = ApiStatusEnum(updated_website.status.value)

        return RollbackConfigResponse(
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
            config_version=rollback_version,
            rolled_back_from_version=current_version,
            rolled_back_to_version=target_version,
            recrawl_job_id=recrawl_job_id,
        )

    async def trigger_crawl(
        self, website_id: str, request: TriggerCrawlRequest
    ) -> TriggerCrawlResponse:
        """Trigger an immediate high-priority crawl job.

        This method:
        1. Validates the website exists and is active
        2. Creates a one-time crawl job with **priority 10** (highest)
        3. Uses the website's base_url as the seed URL
        4. Publishes the job to the queue (front of queue due to high priority)
        5. Returns the job ID and details for tracking

        Args:
            website_id: Website ID to crawl
            request: Trigger request with optional reason and variables

        Returns:
            Trigger response with job details

        Raises:
            ValueError: If website not found or inactive
            RuntimeError: If job creation or publishing fails
        """
        logger.info(
            "triggering_manual_crawl",
            website_id=website_id,
            reason=request.reason,
            has_variables=request.variables is not None,
        )

        # Guard: validate website exists
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found_for_trigger", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Guard: validate website is active
        if website.status != DbStatusEnum.ACTIVE:
            logger.warning(
                "website_inactive_for_trigger",
                website_id=website_id,
                status=website.status.value,
            )
            raise ValueError(f"Website is {website.status.value} and cannot be crawled")

        # Extract max_retries from website config if available
        max_retries = 3  # Default
        if isinstance(website.config, dict):
            global_config = website.config.get("global_config", {})
            if isinstance(global_config, dict):
                retry_config = global_config.get("retry", {})
                if isinstance(retry_config, dict):
                    max_attempts = retry_config.get("max_attempts")
                    if max_attempts is not None:
                        max_retries = max_attempts

        # Create high-priority crawl job
        # Priority 10 = PRIORITY_MANUAL_TRIGGER (highest priority)
        triggered_at = datetime.now(UTC)
        metadata = {"trigger_reason": request.reason} if request.reason else None

        crawl_job = await self.crawl_job_repo.create_template_based_job(
            website_id=website_id,
            seed_url=website.base_url,
            variables=request.variables or {},
            job_type=JobTypeEnum.ONE_TIME,
            priority=PRIORITY_MANUAL_TRIGGER,  # Priority 10 - highest
            scheduled_at=None,  # Immediate execution
            max_retries=max_retries,
            metadata=metadata,
        )

        # Guard: job creation failed
        if not crawl_job:
            logger.error(
                "trigger_job_creation_failed",
                website_id=website_id,
                reason="create_template_based_job returned None",
            )
            raise RuntimeError("Failed to create crawl job")

        logger.info(
            "trigger_job_created",
            job_id=str(crawl_job.id),
            website_id=website_id,
            priority=crawl_job.priority,
            seed_url=website.base_url,
        )

        # Publish job to NATS queue
        job_data = {
            "website_id": str(crawl_job.website_id),
            "seed_url": crawl_job.seed_url,
            "job_type": crawl_job.job_type.value,
            "priority": crawl_job.priority,
            "manual_trigger": True,
        }
        published = await self.nats_queue.publish_job(str(crawl_job.id), job_data)

        # Guard: publish failed
        if not published:
            logger.error(
                "trigger_job_publish_failed",
                job_id=str(crawl_job.id),
                website_id=website_id,
                reason="NATS queue publish returned False",
            )
            raise RuntimeError("Failed to publish job to queue")

        logger.info(
            "trigger_job_published",
            job_id=str(crawl_job.id),
            website_id=website_id,
            priority=crawl_job.priority,
        )

        # Build response
        return TriggerCrawlResponse(
            job_id=crawl_job.id,
            website_id=UUID(website_id),
            seed_url=AnyUrl(website.base_url),
            priority=crawl_job.priority,
            status=CrawlJobStatus.pending,  # Job always starts as pending
            triggered_at=triggered_at,
            message="High-priority crawl job created and queued",
        )

    async def pause_schedule(self, website_id: str) -> ScheduleStatusResponse:
        """Pause scheduled crawls for a website.

        Args:
            website_id: Website ID

        Returns:
            Schedule status response

        Raises:
            ValueError: If website not found or no scheduled job exists
            RuntimeError: If pause operation fails
        """
        logger.info("pausing_schedule", website_id=website_id)

        # Guard: validate website exists
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found_for_pause", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Get scheduled jobs
        scheduled_jobs = await self.scheduled_job_repo.get_by_website_id(website_id)

        # Guard: verify scheduled job exists
        if not scheduled_jobs:
            logger.warning("no_scheduled_job_for_pause", website_id=website_id)
            raise ValueError("No scheduled job found for website")

        # Pause all scheduled jobs (set is_active=False)
        scheduled_job_id = None
        cron_schedule = None
        last_run_time = None

        for job in scheduled_jobs:
            updated_job = await self.scheduled_job_repo.toggle_status(
                job_id=job.id, is_active=False
            )
            if updated_job:
                scheduled_job_id = updated_job.id
                cron_schedule = updated_job.cron_schedule
                last_run_time = updated_job.last_run_time
                logger.info("scheduled_job_paused", job_id=updated_job.id)

        logger.info(
            "schedule_paused",
            website_id=website_id,
            scheduled_job_id=str(scheduled_job_id) if scheduled_job_id else None,
        )

        return ScheduleStatusResponse(
            id=UUID(website_id),
            name=website.name,
            scheduled_job_id=scheduled_job_id,
            is_active=False,
            cron_schedule=cron_schedule,
            next_run_time=None,  # No next run when paused
            last_run_time=last_run_time,
            message=f"Scheduled crawls paused for website '{website.name}'",
        )

    async def resume_schedule(self, website_id: str) -> ScheduleStatusResponse:
        """Resume scheduled crawls for a website.

        Args:
            website_id: Website ID

        Returns:
            Schedule status response

        Raises:
            ValueError: If website not found or no scheduled job exists
            RuntimeError: If resume operation fails
        """
        logger.info("resuming_schedule", website_id=website_id)

        # Guard: validate website exists
        website = await self.website_repo.get_by_id(website_id)
        if not website:
            logger.warning("website_not_found_for_resume", website_id=website_id)
            raise ValueError(f"Website with ID '{website_id}' not found")

        # Get scheduled jobs
        scheduled_jobs = await self.scheduled_job_repo.get_by_website_id(website_id)

        # Guard: verify scheduled job exists
        if not scheduled_jobs:
            logger.warning("no_scheduled_job_for_resume", website_id=website_id)
            raise ValueError("No scheduled job found for website")

        # Resume all scheduled jobs (set is_active=True and recalculate next_run_time)
        scheduled_job_id = None
        cron_schedule = None
        next_run_time = None
        last_run_time = None

        for job in scheduled_jobs:
            # Calculate next run time from cron schedule in job's timezone
            # Use timezone from job (defaults to UTC if not set on old jobs)
            job_timezone = job.timezone if hasattr(job, "timezone") and job.timezone else "UTC"

            is_valid, result = validate_and_calculate_next_run(
                job.cron_schedule, timezone=job_timezone
            )
            if is_valid and isinstance(result, datetime):
                next_run_time = result
            else:
                # Fallback to current time + 1 day if cron validation fails
                next_run_time = datetime.now(UTC) + timedelta(days=1)

            # Update job with is_active=True and new next_run_time
            updated_job = await self.scheduled_job_repo.update(
                job_id=job.id, is_active=True, next_run_time=next_run_time
            )

            if updated_job:
                scheduled_job_id = updated_job.id
                cron_schedule = updated_job.cron_schedule
                last_run_time = updated_job.last_run_time
                logger.info(
                    "scheduled_job_resumed",
                    job_id=updated_job.id,
                    next_run_time=next_run_time.isoformat() if next_run_time else None,
                )

        logger.info(
            "schedule_resumed",
            website_id=website_id,
            scheduled_job_id=str(scheduled_job_id) if scheduled_job_id else None,
            next_run_time=next_run_time.isoformat() if next_run_time else None,
        )

        return ScheduleStatusResponse(
            id=UUID(website_id),
            name=website.name,
            scheduled_job_id=scheduled_job_id,
            is_active=True,
            cron_schedule=cron_schedule,
            next_run_time=next_run_time,
            last_run_time=last_run_time,
            message=f"Scheduled crawls resumed for website '{website.name}'",
        )
