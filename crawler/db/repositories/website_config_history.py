"""Website config history repository using sqlc-generated queries."""

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import models, website_config_history

from .base import to_uuid


class WebsiteConfigHistoryRepository:
    """Repository for website config history operations."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = website_config_history.AsyncQuerier(connection)

    async def create(
        self,
        website_id: str | UUID,
        version: int,
        config: dict,
        changed_by: str | None = None,
        change_reason: str | None = None,
    ) -> models.WebsiteConfigHistory | None:
        """Create a new config history entry.

        Args:
            website_id: Website ID
            version: Version number
            config: Configuration snapshot
            changed_by: Who made the change
            change_reason: Why the change was made

        Returns:
            Created WebsiteConfigHistory model or None
        """
        return await self._querier.create_config_history(
            website_id=to_uuid(website_id),
            version=version,
            config=json.dumps(config),
            changed_by=changed_by,
            change_reason=change_reason,
        )

    async def get_latest_version(self, website_id: str | UUID) -> int:
        """Get the latest version number for a website.

        Args:
            website_id: Website ID

        Returns:
            Latest version number (0 if no history exists)
        """
        result = await self._querier.get_latest_config_version(website_id=to_uuid(website_id))
        return result.latest_version if result else 0

    async def list_history(
        self, website_id: str | UUID, limit: int = 10, offset: int = 0
    ) -> list[models.WebsiteConfigHistory]:
        """List configuration history for a website.

        Args:
            website_id: Website ID
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of WebsiteConfigHistory models (newest first)
        """
        history = []
        async for entry in self._querier.get_config_history(
            website_id=to_uuid(website_id), limit_count=limit, offset_count=offset
        ):
            history.append(entry)
        return history

    async def get_by_version(
        self, website_id: str | UUID, version: int
    ) -> models.WebsiteConfigHistory | None:
        """Get a specific version of the configuration.

        Args:
            website_id: Website ID
            version: Version number

        Returns:
            WebsiteConfigHistory model or None if not found
        """
        return await self._querier.get_config_by_version(
            website_id=to_uuid(website_id), version=version
        )
