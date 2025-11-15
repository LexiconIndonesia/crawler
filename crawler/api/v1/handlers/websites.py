"""Website request handlers with dependency injection.

This module contains HTTP handlers that coordinate between FastAPI routes
and business logic services using dependency injection.
"""

from datetime import UTC, datetime

from fastapi import HTTPException, status

from crawler.api.generated import (
    ConfigHistoryListResponse,
    ConfigHistoryResponse,
    CreateWebsiteRequest,
    DeleteWebsiteResponse,
    ListWebsitesResponse,
    RollbackConfigRequest,
    RollbackConfigResponse,
    TriggerCrawlRequest,
    TriggerCrawlResponse,
    UpdateWebsiteRequest,
    UpdateWebsiteResponse,
    WebsiteResponse,
    WebsiteWithStatsResponse,
)
from crawler.api.v1.decorators import handle_service_errors
from crawler.api.v1.services import WebsiteService
from crawler.api.validators import validate_and_calculate_next_run
from crawler.core.logging import get_logger

logger = get_logger(__name__)


@handle_service_errors(operation="creating the website")
async def create_website_handler(
    request: CreateWebsiteRequest,
    website_service: WebsiteService,
) -> WebsiteResponse:
    """Handle website creation with configuration and scheduling.

    This handler validates the request, delegates business logic to the service,
    and translates service exceptions to HTTP responses via the decorator.

    Args:
        request: Website creation request with configuration
        website_service: Injected website service

    Returns:
        Created website with scheduling information

    Raises:
        HTTPException: If validation fails or operation fails
    """
    logger.info("create_website_request", website_name=request.name, base_url=request.base_url)

    # Validate cron schedule - use default if not provided (bi-weekly)
    cron_schedule = request.schedule.cron or "0 0 1,15 * *"
    is_valid, result = validate_and_calculate_next_run(cron_schedule)
    if not is_valid:
        logger.warning(
            "invalid_cron_expression",
            cron=request.schedule.cron,
            error=result,
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid cron expression: {result}",
        )

    next_run_time = result if isinstance(result, datetime) else datetime.now(UTC)

    # TODO(auth): Pass authenticated user identifier to service
    # Once authentication is implemented, extract user ID from request context
    # and pass to service: created_by=current_user.id
    # This will populate website.created_by for audit trail

    # Delegate to service layer (error handling done by decorator)
    return await website_service.create_website(request, next_run_time)


@handle_service_errors(operation="retrieving the website")
async def get_website_by_id_handler(
    website_id: str,
    website_service: WebsiteService,
) -> WebsiteWithStatsResponse:
    """Handle website retrieval by ID with statistics.

    This handler delegates to the service layer which handles:
    - Website lookup
    - Statistics calculation
    - Scheduled job info retrieval

    Args:
        website_id: Website ID
        website_service: Injected website service

    Returns:
        Website with statistics

    Raises:
        HTTPException: If website not found or operation fails
    """
    logger.info("get_website_by_id_request", website_id=website_id)

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400, RuntimeError -> 500
    return await website_service.get_website_by_id(website_id)


@handle_service_errors(operation="listing websites")
async def list_websites_handler(
    status: str | None,
    limit: int,
    offset: int,
    website_service: WebsiteService,
) -> ListWebsitesResponse:
    """Handle website listing with pagination and filtering.

    This handler validates query parameters and delegates to the service layer.

    Args:
        status: Optional status filter ('active' or 'inactive')
        limit: Maximum number of results
        offset: Number of results to skip
        website_service: Injected website service

    Returns:
        Paginated list of websites

    Raises:
        HTTPException: If invalid parameters or operation fails
    """
    logger.info("list_websites_request", status=status, limit=limit, offset=offset)

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400, RuntimeError -> 500
    return await website_service.list_websites(status=status, limit=limit, offset=offset)


@handle_service_errors(operation="updating the website")
async def update_website_handler(
    website_id: str,
    request: UpdateWebsiteRequest,
    website_service: WebsiteService,
) -> UpdateWebsiteResponse:
    """Handle website update with versioning.

    This handler validates and delegates to the service layer which handles:
    - Configuration validation
    - History versioning
    - Schedule updates
    - Optional re-crawl triggering

    Args:
        website_id: Website ID
        request: Update request
        website_service: Injected website service

    Returns:
        Updated website with version info

    Raises:
        HTTPException: If website not found or validation fails
    """
    logger.info("update_website_request", website_id=website_id)

    # TODO(auth): Pass authenticated user identifier to changed_by parameter
    # Once authentication is implemented, extract user ID from request context
    # and pass to service: changed_by=current_user.id
    # This will populate website_config_history.changed_by for audit trail

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400, RuntimeError -> 500
    return await website_service.update_website(website_id, request)


@handle_service_errors(operation="deleting the website")
async def delete_website_handler(
    website_id: str,
    delete_data: bool,
    website_service: WebsiteService,
) -> DeleteWebsiteResponse:
    """Handle website deletion with soft delete.

    This handler validates and delegates to the service layer which handles:
    - Soft delete (sets deleted_at timestamp)
    - Cancels all running/pending jobs
    - Archives configuration for audit
    - Disables scheduled jobs

    Args:
        website_id: Website ID
        delete_data: Whether to delete all crawled data
        website_service: Injected website service

    Returns:
        Deletion summary with cancelled jobs and archived config version

    Raises:
        HTTPException: If website not found or already deleted
    """
    logger.info("delete_website_request", website_id=website_id, delete_data=delete_data)

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400, RuntimeError -> 500
    return await website_service.delete_website(website_id, delete_data)


@handle_service_errors(operation="retrieving configuration history")
async def get_config_history_handler(
    website_id: str,
    limit: int,
    offset: int,
    website_service: WebsiteService,
) -> ConfigHistoryListResponse:
    """Handle configuration history retrieval.

    This handler delegates to the service layer to retrieve the configuration
    version history for a website.

    Args:
        website_id: Website ID
        limit: Maximum number of versions to return
        offset: Number of versions to skip
        website_service: Injected website service

    Returns:
        Paginated list of configuration versions

    Raises:
        HTTPException: If website not found or operation fails
    """
    logger.info("get_config_history_request", website_id=website_id, limit=limit, offset=offset)

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400, RuntimeError -> 500
    return await website_service.get_config_history(website_id, limit, offset)


@handle_service_errors(operation="retrieving configuration version")
async def get_config_version_handler(
    website_id: str,
    version: int,
    website_service: WebsiteService,
) -> ConfigHistoryResponse:
    """Handle specific configuration version retrieval.

    This handler delegates to the service layer to retrieve a specific
    configuration version.

    Args:
        website_id: Website ID
        version: Version number to retrieve
        website_service: Injected website service

    Returns:
        Configuration version details

    Raises:
        HTTPException: If website or version not found
    """
    logger.info("get_config_version_request", website_id=website_id, version=version)

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400, RuntimeError -> 500
    return await website_service.get_config_version(website_id, version)


@handle_service_errors(operation="rolling back configuration")
async def rollback_config_handler(
    website_id: str,
    request: RollbackConfigRequest,
    website_service: WebsiteService,
) -> RollbackConfigResponse:
    """Handle configuration rollback to a previous version.

    This handler validates and delegates to the service layer which handles:
    - Validation that target version exists
    - Saving current config to history
    - Restoring configuration from target version
    - Updating scheduled jobs if needed
    - Optional re-crawl triggering

    Args:
        website_id: Website ID
        request: Rollback request with target version, reason, and recrawl flag
        website_service: Injected website service

    Returns:
        Rollback response with updated website and version info

    Raises:
        HTTPException: If website or version not found, or rollback fails
    """
    logger.info(
        "rollback_config_request",
        website_id=website_id,
        version=request.version,
        trigger_recrawl=request.trigger_recrawl,
    )

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400, RuntimeError -> 500
    return await website_service.rollback_config(website_id, request.version, request)


@handle_service_errors(operation="triggering crawl")
async def trigger_crawl_handler(
    website_id: str,
    request: TriggerCrawlRequest,
    website_service: WebsiteService,
) -> TriggerCrawlResponse:
    """Handle manual trigger of high-priority crawl job.

    This handler creates an immediate, high-priority crawl job for the specified website.
    The job is created with priority 10 (highest) and pushed to the front of the queue.

    Args:
        website_id: Website ID to crawl
        request: Trigger request with optional reason and variables
        website_service: Injected website service

    Returns:
        Trigger response with job details and confirmation

    Raises:
        HTTPException: If website not found, inactive, or job creation/publish fails
    """
    logger.info(
        "trigger_crawl_request",
        website_id=website_id,
        reason=request.reason,
        has_variables=request.variables is not None,
    )

    # Delegate to service layer (error handling done by decorator)
    # ValueError -> 400 (website not found or inactive)
    # RuntimeError -> 500 (job creation or publish failure)
    return await website_service.trigger_crawl(website_id, request)
