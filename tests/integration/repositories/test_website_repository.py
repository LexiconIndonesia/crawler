"""Integration tests for WebsiteRepository.

These tests require a running PostgreSQL database.
Run with: make test-integration
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.generated.models import StatusEnum
from crawler.db.repositories import WebsiteRepository


@pytest.mark.asyncio
class TestWebsiteRepository:
    """Tests for WebsiteRepository."""

    async def test_create_and_get_website(self, db_session: AsyncSession) -> None:
        """Test creating and retrieving a website."""
        repo = WebsiteRepository(await db_session.connection())

        # Create website
        website = await repo.create(
            name="test-site",
            base_url="https://example.com",
            config={"max_depth": 3},
            created_by="test@example.com",
        )

        assert website.name == "test-site"
        assert website.base_url == "https://example.com"
        assert website.config == {"max_depth": 3}
        assert website.created_by == "test@example.com"
        assert website.status == StatusEnum.ACTIVE

        # Get by ID
        fetched = await repo.get_by_id(str(website.id))
        assert fetched is not None
        assert fetched.name == "test-site"

        # Get by name
        fetched_by_name = await repo.get_by_name("test-site")
        assert fetched_by_name is not None
        assert str(fetched_by_name.id) == str(website.id)

    async def test_update_website(self, db_session: AsyncSession) -> None:
        """Test updating a website."""
        repo = WebsiteRepository(await db_session.connection())

        website = await repo.create(name="update-test", base_url="https://example.com", config={})

        updated = await repo.update(
            str(website.id), status=StatusEnum.INACTIVE, config={"new_field": "value"}
        )

        assert updated is not None
        assert updated.status == StatusEnum.INACTIVE
        assert updated.config == {"new_field": "value"}

    async def test_list_websites(self, db_session: AsyncSession) -> None:
        """Test listing websites."""
        repo = WebsiteRepository(await db_session.connection())

        # Create multiple websites
        await repo.create(name="site1", base_url="https://site1.com", config={})
        await repo.create(name="site2", base_url="https://site2.com", config={})
        await repo.create(
            name="site3", base_url="https://site3.com", config={}, status=StatusEnum.INACTIVE
        )

        # List all active
        active_sites = await repo.list(status=StatusEnum.ACTIVE, limit=10)
        assert len(active_sites) >= 2

        # Count
        count = await repo.count(status=StatusEnum.ACTIVE)
        assert count >= 2
