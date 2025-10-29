"""Website service with business logic."""

from datetime import datetime

from pydantic import AnyUrl

from crawler.api.generated import (
    CreateWebsiteRequest,
    WebsiteResponse,
)
from crawler.api.generated import (
    StatusEnum as ApiStatusEnum,
)
from crawler.core.logging import get_logger
from crawler.db.repositories import ScheduledJobRepository, WebsiteRepository

logger = get_logger(__name__)


class WebsiteService:
    """Service for website operations with dependency injection."""

    def __init__(
        self,
        website_repo: WebsiteRepository,
        scheduled_job_repo: ScheduledJobRepository,
    ):
        """Initialize service with dependencies.

        Args:
            website_repo: Website repository for database access
            scheduled_job_repo: Scheduled job repository for database access
        """
        self.website_repo = website_repo
        self.scheduled_job_repo = scheduled_job_repo

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
