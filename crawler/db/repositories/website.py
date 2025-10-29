"""Website repository using sqlc-generated queries."""

import json
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.generated import models, website
from crawler.db.generated.models import StatusEnum

from .base import to_uuid


class WebsiteRepository:
    """Repository for website operations using sqlc-generated queries."""

    def __init__(self, connection: AsyncConnection):
        """Initialize repository.

        Args:
            connection: SQLAlchemy async connection.
        """
        self.conn = connection
        self._querier = website.AsyncQuerier(connection)

    async def create(
        self,
        name: str,
        base_url: str,
        config: dict[str, Any],
        cron_schedule: str = "0 0 1,15 * *",
        created_by: str | None = None,
        status: StatusEnum = StatusEnum.ACTIVE,
    ) -> models.Website | None:
        """Create a new website.

        Args:
            name: Website name
            base_url: Base URL
            config: Configuration dict (will be serialized to JSON)
            cron_schedule: Cron schedule (defaults to bi-weekly: 1st and 15th at midnight)
            created_by: Optional creator identifier
            status: Status enum (defaults to ACTIVE)

        Returns:
            Created Website model or None
        """
        return await self._querier.create_website(
            name=name,
            base_url=base_url,
            config=json.dumps(config),
            cron_schedule=cron_schedule,
            created_by=created_by,
            status=status,
        )

    async def get_by_id(self, website_id: str | UUID) -> models.Website | None:
        """Get website by ID."""
        return await self._querier.get_website_by_id(id=to_uuid(website_id))

    async def get_by_name(self, name: str) -> models.Website | None:
        """Get website by name."""
        return await self._querier.get_website_by_name(name=name)

    async def list(
        self, status: StatusEnum | None = None, limit: int = 100, offset: int = 0
    ) -> list[models.Website]:
        """List websites with pagination.

        Args:
            status: Optional status filter (None returns all)
            limit: Maximum number of results
            offset: Number of results to skip

        Returns:
            List of Website models

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        websites = []
        # sqlc generates non-optional but SQL supports COALESCE (optional filter)
        async for website_obj in self._querier.list_websites(
            status=status,  # type: ignore[arg-type]
            limit_count=limit,
            offset_count=offset,
        ):
            websites.append(website_obj)
        return websites

    async def count(self, status: StatusEnum | None = None) -> int:
        """Count websites.

        Args:
            status: Optional status filter (None counts all)

        Returns:
            Count of websites

        Note:
            SQL uses COALESCE, but sqlc generates non-optional type.
        """
        # sqlc generates non-optional but SQL supports COALESCE (optional filter)
        result = await self._querier.count_websites(status=status)  # type: ignore[arg-type]
        return result if result is not None else 0

    async def update(
        self,
        website_id: str | UUID,
        name: str | None = None,
        base_url: str | None = None,
        config: dict[str, Any] | None = None,
        cron_schedule: str | None = None,
        status: StatusEnum | None = None,
    ) -> models.Website | None:
        """Update website fields.

        Args:
            website_id: Website ID
            name: New name (optional, uses existing if None)
            base_url: New base URL (optional, uses existing if None)
            config: New config dict (optional, uses existing if None, will be serialized to JSON)
            cron_schedule: New cron schedule (optional, uses existing if None)
            status: New status (optional, uses existing if None)

        Returns:
            Updated Website model or None

        Note:
            SQL uses COALESCE for all parameters, but sqlc generates non-optional types.
            We accept Optional here to match the SQL behavior.
        """
        # sqlc generates non-optional types but SQL supports COALESCE (optional updates)
        return await self._querier.update_website(  # type: ignore[arg-type]
            id=to_uuid(website_id),
            name=name,  # type: ignore[arg-type]
            base_url=base_url,  # type: ignore[arg-type]
            config=json.dumps(config) if config else None,
            cron_schedule=cron_schedule,  # type: ignore[arg-type]
            status=status,  # type: ignore[arg-type]
        )

    async def delete(self, website_id: str | UUID) -> None:
        """Delete website."""
        await self._querier.delete_website(id=to_uuid(website_id))
