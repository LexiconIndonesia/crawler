"""Job service with business logic."""

from typing import Any

from pydantic import AnyUrl

from crawler.api.generated import (
    CreateSeedJobInlineRequest,
    CreateSeedJobRequest,
    JobType,
    SeedJobResponse,
)
from crawler.api.schemas import StatusEnum as ApiStatusEnum
from crawler.core.logging import get_logger
from crawler.db.generated.models import JobTypeEnum, StatusEnum
from crawler.db.repositories import CrawlJobRepository, WebsiteRepository

logger = get_logger(__name__)


class JobService:
    """Service for crawl job operations with dependency injection."""

    def __init__(
        self,
        crawl_job_repo: CrawlJobRepository,
        website_repo: WebsiteRepository,
    ):
        """Initialize service with dependencies.

        Args:
            crawl_job_repo: Crawl job repository for database access
            website_repo: Website repository for template loading
        """
        self.crawl_job_repo = crawl_job_repo
        self.website_repo = website_repo

    async def create_seed_job(self, request: CreateSeedJobRequest) -> SeedJobResponse:
        """Create a new crawl job using a website template.

        This method:
        1. Validates that the website template exists
        2. Checks that the website is active
        3. Creates a template-based crawl job with the seed URL
        4. Returns the job details

        Args:
            request: Seed job creation request

        Returns:
            Created seed job response

        Raises:
            ValueError: If website not found or inactive
            RuntimeError: If job creation fails
        """
        logger.info(
            "creating_seed_job",
            website_id=str(request.website_id),
            seed_url=str(request.seed_url),
            priority=request.priority,
        )

        # Load website template from database
        website = await self.website_repo.get_by_id(request.website_id)
        if not website:
            logger.warning("website_not_found", website_id=str(request.website_id))
            raise ValueError(f"Website with ID '{request.website_id}' not found")

        # Check if website is active
        if website.status != StatusEnum.ACTIVE:
            logger.warning(
                "website_inactive",
                website_id=str(request.website_id),
                website_name=website.name,
                status=website.status.value,
            )
            raise ValueError(f"Website '{website.name}' is inactive and cannot be used")

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

        logger.debug(
            "max_retries_set_from_template",
            website_id=str(request.website_id),
            max_retries=max_retries,
        )

        # Create template-based job
        # Convert seed_url from AnyUrl to string for database storage
        job = await self.crawl_job_repo.create_template_based_job(
            website_id=request.website_id,
            seed_url=str(request.seed_url),
            variables=request.variables,
            job_type=JobTypeEnum.ONE_TIME,  # Seed submissions are always one-time jobs
            priority=request.priority,
            scheduled_at=None,  # Seed jobs execute immediately (not scheduled)
            max_retries=max_retries,
            metadata=None,
        )

        if not job:
            logger.error(
                "job_creation_failed",
                website_id=str(request.website_id),
                seed_url=str(request.seed_url),
            )
            raise RuntimeError("Failed to create crawl job")

        logger.info(
            "seed_job_created",
            job_id=str(job.id),
            website_id=str(request.website_id),
            seed_url=str(request.seed_url),
            priority=job.priority,
        )

        # Build response - convert database enum to API enum
        api_status = ApiStatusEnum(job.status.value)
        job_type = JobType(job.job_type.value)

        # Ensure website_id is not None (it shouldn't be for template-based jobs)
        assert job.website_id is not None, "website_id should not be None for template-based jobs"

        return SeedJobResponse(
            id=job.id,
            website_id=job.website_id,
            seed_url=AnyUrl(job.seed_url),
            status=api_status,
            job_type=job_type,
            priority=job.priority,
            scheduled_at=job.scheduled_at,
            variables=job.variables,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )

    async def create_seed_job_inline(self, request: CreateSeedJobInlineRequest) -> SeedJobResponse:
        """Create a new crawl job with inline configuration.

        This method:
        1. Validates the inline configuration
        2. Creates an inline config job (no website template)
        3. Returns the job details

        Args:
            request: Seed job creation request with inline configuration

        Returns:
            Created seed job response

        Raises:
            ValueError: If configuration is invalid
            RuntimeError: If job creation fails
        """
        logger.info(
            "creating_seed_job_inline",
            seed_url=str(request.seed_url),
            priority=request.priority,
            num_steps=len(request.steps),
        )

        # Build inline configuration from request
        # Convert Pydantic models to dict for JSON storage
        inline_config: dict[str, Any] = {
            "steps": [step.model_dump(mode="json", exclude_none=True) for step in request.steps],
            "global_config": request.global_config.model_dump(mode="json", exclude_none=True),
        }

        logger.debug(
            "inline_config_prepared",
            seed_url=str(request.seed_url),
            config_keys=list(inline_config.keys()),
            steps_count=len(inline_config["steps"]),
        )

        # Extract max_retries from global_config.retry.max_attempts if available
        max_retries = 3  # Default
        if request.global_config.retry and request.global_config.retry.max_attempts is not None:
            max_retries = request.global_config.retry.max_attempts

        logger.debug(
            "max_retries_set",
            seed_url=str(request.seed_url),
            max_retries=max_retries,
            from_config=request.global_config.retry is not None,
        )

        # Create inline config job (no website_id)
        job = await self.crawl_job_repo.create_seed_url_submission(
            seed_url=str(request.seed_url),
            inline_config=inline_config,
            variables=request.variables,
            job_type=JobTypeEnum.ONE_TIME,  # Inline submissions are always one-time jobs
            priority=request.priority,
            scheduled_at=None,  # Inline jobs execute immediately (not scheduled)
            max_retries=max_retries,
            metadata=None,
        )

        if not job:
            logger.error(
                "job_creation_failed",
                seed_url=str(request.seed_url),
            )
            raise RuntimeError("Failed to create crawl job")

        logger.info(
            "seed_job_inline_created",
            job_id=str(job.id),
            seed_url=str(request.seed_url),
            priority=job.priority,
        )

        # Build response - convert database enum to API enum
        api_status = ApiStatusEnum(job.status.value)
        job_type = JobType(job.job_type.value)

        return SeedJobResponse(
            id=job.id,
            website_id=None,  # Inline config jobs don't have website_id
            seed_url=AnyUrl(job.seed_url),
            status=api_status,
            job_type=job_type,
            priority=job.priority,
            scheduled_at=job.scheduled_at,
            variables=job.variables,
            created_at=job.created_at,
            updated_at=job.updated_at,
        )
