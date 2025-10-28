"""Integration tests for crawl_job table constraint validation.

Tests the mutual exclusivity constraint between website_id and inline_config.
Application-level validation is tested here, with database constraint as backup.
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from crawler.db.repositories import CrawlJobRepository, WebsiteRepository


@pytest.mark.asyncio
class TestCrawlJobConstraint:
    """Tests for crawl_job table constraints."""

    async def test_cannot_have_both_website_id_and_inline_config(
        self, db_session: AsyncSession
    ) -> None:
        """Test that setting both website_id and inline_config raises validation error.

        Note: Application-level validation catches this before hitting the database.
        The database constraint (ck_crawl_job_config_source) serves as a backup.
        """
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        # Create a website
        website = await website_repo.create(
            name="constraint-test-site",
            base_url="https://test.com",
            config={"method": "api"},
        )

        # Try to create a job with BOTH website_id AND inline_config
        # Application-level validation should catch this and raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await job_repo.create(
                seed_url="https://test.com",
                website_id=str(website.id),  # Setting website_id
                inline_config={"method": "browser"},  # AND inline_config - NOT ALLOWED!
            )

        # Verify the error message explains the issue
        assert "Cannot specify both website_id and inline_config" in str(exc_info.value)

    async def test_cannot_have_neither_website_id_nor_inline_config(
        self, db_session: AsyncSession
    ) -> None:
        """Test that having neither website_id nor inline_config raises validation error.

        Note: Application-level validation catches this before hitting the database.
        The database constraint (ck_crawl_job_config_source) serves as a backup.
        """
        conn = await db_session.connection()
        job_repo = CrawlJobRepository(conn)

        # Try to create a job with NEITHER website_id NOR inline_config
        # Application-level validation should catch this and raise ValueError
        with pytest.raises(ValueError) as exc_info:
            await job_repo.create(
                seed_url="https://test.com",
                # No website_id
                # No inline_config
                # This violates the constraint!
            )

        # Verify the error message explains the issue
        assert "Must specify either website_id or inline_config" in str(exc_info.value)

    async def test_can_have_website_id_only(self, db_session: AsyncSession) -> None:
        """Test that having only website_id is valid."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        # Create a website
        website = await website_repo.create(
            name="valid-template-site",
            base_url="https://test.com",
            config={"method": "api"},
        )

        # Create a job with ONLY website_id - should succeed
        job = await job_repo.create(
            seed_url="https://test.com",
            website_id=str(website.id),  # Only website_id
            # No inline_config
        )

        assert job is not None
        assert str(job.website_id) == str(website.id)
        assert job.inline_config is None

    async def test_can_have_inline_config_only(self, db_session: AsyncSession) -> None:
        """Test that having only inline_config is valid."""
        conn = await db_session.connection()
        job_repo = CrawlJobRepository(conn)

        # Create a job with ONLY inline_config - should succeed
        job = await job_repo.create(
            seed_url="https://test.com",
            # No website_id
            inline_config={"method": "browser", "timeout": 30},  # Only inline_config
        )

        assert job is not None
        assert job.website_id is None
        assert job.inline_config == {"method": "browser", "timeout": 30}

    async def test_template_based_job_creation_validates_constraint(
        self, db_session: AsyncSession
    ) -> None:
        """Test that create_template_based_job enforces the constraint."""
        conn = await db_session.connection()
        website_repo = WebsiteRepository(conn)
        job_repo = CrawlJobRepository(conn)

        # Create a website
        website = await website_repo.create(
            name="template-constraint-test",
            base_url="https://test.com",
            config={"method": "api"},
        )

        # Use template-based creation - should set only website_id
        job = await job_repo.create_template_based_job(
            website_id=str(website.id),
            seed_url="https://test.com/page",
        )

        assert job is not None
        assert str(job.website_id) == str(website.id)
        assert job.inline_config is None  # Should not have inline_config

    async def test_seed_url_submission_validates_constraint(self, db_session: AsyncSession) -> None:
        """Test that create_seed_url_submission enforces the constraint."""
        conn = await db_session.connection()
        job_repo = CrawlJobRepository(conn)

        # Use seed URL submission - should set only inline_config
        job = await job_repo.create_seed_url_submission(
            seed_url="https://test.com",
            inline_config={"method": "browser"},
        )

        assert job is not None
        assert job.website_id is None  # Should not have website_id
        assert job.inline_config == {"method": "browser"}
