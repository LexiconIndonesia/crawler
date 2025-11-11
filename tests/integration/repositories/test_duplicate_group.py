"""Integration tests for DuplicateGroupRepository."""

import pytest
from sqlalchemy.ext.asyncio import AsyncConnection

from crawler.db.repositories.crawled_page import CrawledPageRepository
from crawler.db.repositories.duplicate_group import DuplicateGroupRepository
from crawler.db.repositories.website import WebsiteRepository


@pytest.fixture
async def website_repo(db_connection: AsyncConnection) -> WebsiteRepository:
    """Create WebsiteRepository instance."""
    return WebsiteRepository(db_connection)


@pytest.fixture
async def crawled_page_repo(db_connection: AsyncConnection) -> CrawledPageRepository:
    """Create CrawledPageRepository instance."""
    return CrawledPageRepository(db_connection)


@pytest.fixture
async def duplicate_group_repo(db_connection: AsyncConnection) -> DuplicateGroupRepository:
    """Create DuplicateGroupRepository instance."""
    return DuplicateGroupRepository(db_connection)


@pytest.fixture
async def test_website(website_repo: WebsiteRepository):
    """Create a test website."""
    import uuid

    return await website_repo.create(
        name=f"Test Site {uuid.uuid4()}", base_url="https://example.com", config={}
    )


@pytest.fixture
async def test_crawl_job(db_connection: AsyncConnection, test_website):
    """Create a test crawl job."""
    from crawler.db.repositories.crawl_job import CrawlJobRepository

    crawl_job_repo = CrawlJobRepository(db_connection)
    return await crawl_job_repo.create_template_based_job(
        seed_url="https://example.com", website_id=str(test_website.id)
    )


@pytest.fixture
async def canonical_page(crawled_page_repo: CrawledPageRepository, test_website, test_crawl_job):
    """Create a canonical (original) page."""
    from datetime import UTC, datetime

    return await crawled_page_repo.create(
        website_id=str(test_website.id),
        job_id=str(test_crawl_job.id),
        url="https://example.com/original",
        url_hash="hash_original",
        content_hash="content_hash_original",
        crawled_at=datetime.now(UTC),
        extracted_content="Original content",
    )


@pytest.fixture
async def duplicate_page1(crawled_page_repo: CrawledPageRepository, test_website, test_crawl_job):
    """Create first duplicate page."""
    from datetime import UTC, datetime

    return await crawled_page_repo.create(
        website_id=str(test_website.id),
        job_id=str(test_crawl_job.id),
        url="https://example.com/dup1",
        url_hash="hash_dup1",
        content_hash="content_hash_dup1",
        crawled_at=datetime.now(UTC),
        extracted_content="Duplicate content",
    )


@pytest.fixture
async def duplicate_page2(crawled_page_repo: CrawledPageRepository, test_website, test_crawl_job):
    """Create second duplicate page."""
    from datetime import UTC, datetime

    return await crawled_page_repo.create(
        website_id=str(test_website.id),
        job_id=str(test_crawl_job.id),
        url="https://example.com/dup2",
        url_hash="hash_dup2",
        content_hash="content_hash_dup2",
        crawled_at=datetime.now(UTC),
        extracted_content="Another duplicate",
    )


class TestDuplicateGroupRepository:
    """Test suite for DuplicateGroupRepository."""

    async def test_create_duplicate_group(
        self, duplicate_group_repo: DuplicateGroupRepository, canonical_page
    ) -> None:
        """Test creating a new duplicate group."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        assert group is not None
        assert str(group.canonical_page_id) == str(canonical_page.id)
        assert group.group_size == 1  # Initially just the canonical page
        assert group.created_at is not None
        assert group.updated_at is not None

    async def test_get_group(
        self, duplicate_group_repo: DuplicateGroupRepository, canonical_page
    ) -> None:
        """Test retrieving a group by ID."""
        created_group = await duplicate_group_repo.create_group(str(canonical_page.id))
        retrieved_group = await duplicate_group_repo.get_group(str(created_group.id))

        assert retrieved_group is not None
        assert retrieved_group.id == created_group.id
        assert str(retrieved_group.canonical_page_id) == str(canonical_page.id)

    async def test_get_group_by_canonical_page(
        self, duplicate_group_repo: DuplicateGroupRepository, canonical_page
    ) -> None:
        """Test retrieving a group by canonical page."""
        created_group = await duplicate_group_repo.create_group(str(canonical_page.id))
        retrieved_group = await duplicate_group_repo.get_group_by_canonical_page(
            str(canonical_page.id)
        )

        assert retrieved_group is not None
        assert retrieved_group.id == created_group.id

    async def test_add_duplicate_exact_hash(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test adding a duplicate with exact hash match."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        relationship = await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
            similarity_score=100,
            detected_by="test_suite",
        )

        assert relationship is not None
        assert str(relationship.group_id) == str(group.id)
        assert str(relationship.duplicate_page_id) == str(duplicate_page1.id)
        assert relationship.detection_method == "exact_hash"
        assert relationship.similarity_score == 100
        assert relationship.detected_by == "test_suite"

        # Verify group_size was updated by trigger
        updated_group = await duplicate_group_repo.get_group(str(group.id))
        assert updated_group.group_size == 2  # canonical + 1 duplicate

    async def test_add_duplicate_fuzzy_match(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test adding a duplicate with fuzzy match."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        relationship = await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="fuzzy_match",
            similarity_score=95,
            confidence_threshold=3,  # Hamming distance
            detected_by="simhash_detector",
        )

        assert relationship.detection_method == "fuzzy_match"
        assert relationship.similarity_score == 95
        assert relationship.confidence_threshold == 3

    async def test_add_duplicate_invalid_method(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test that invalid detection method raises error."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        with pytest.raises(ValueError, match="Invalid detection_method"):
            await duplicate_group_repo.add_duplicate(
                group_id=str(group.id),
                duplicate_page_id=str(duplicate_page1.id),
                detection_method="invalid_method",
            )

    async def test_list_duplicates_in_group(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
        duplicate_page2,
    ) -> None:
        """Test listing all duplicates in a group."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        # Add two duplicates
        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
            similarity_score=100,
        )

        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page2.id),
            detection_method="fuzzy_match",
            similarity_score=95,
        )

        # List duplicates
        duplicates = await duplicate_group_repo.list_duplicates_in_group(str(group.id))

        assert len(duplicates) == 2
        assert duplicates[0].url in [duplicate_page1.url, duplicate_page2.url]
        assert duplicates[1].url in [duplicate_page1.url, duplicate_page2.url]
        assert duplicates[0].content_hash is not None

    async def test_find_group_for_page(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test finding which group a page belongs to."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
        )

        # Find group for duplicate page
        found_group = await duplicate_group_repo.find_group_for_page(str(duplicate_page1.id))

        assert found_group is not None
        assert found_group.id == group.id
        assert str(found_group.canonical_page_id) == str(canonical_page.id)

    async def test_get_group_with_canonical(
        self, duplicate_group_repo: DuplicateGroupRepository, canonical_page
    ) -> None:
        """Test getting group with canonical page details."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        group_with_canonical = await duplicate_group_repo.get_group_with_canonical(str(group.id))

        assert group_with_canonical is not None
        assert group_with_canonical.canonical_url == canonical_page.url
        assert group_with_canonical.canonical_content_hash == canonical_page.content_hash
        assert group_with_canonical.canonical_crawled_at is not None

    async def test_get_group_stats(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
        duplicate_page2,
    ) -> None:
        """Test getting statistics for a group."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        # Add duplicates with different similarity scores
        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
            similarity_score=100,
        )

        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page2.id),
            detection_method="fuzzy_match",
            similarity_score=90,
        )

        # Get stats
        stats = await duplicate_group_repo.get_group_stats(str(group.id))

        assert stats is not None
        assert stats.group_size == 3  # canonical + 2 duplicates
        assert stats.relationship_count == 2  # Only explicit relationships
        assert stats.avg_similarity == 95.0  # (100 + 90) / 2
        assert stats.first_detected is not None
        assert stats.last_detected is not None

    async def test_remove_relationship(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test removing a duplicate relationship."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        relationship = await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
        )

        # Verify group_size before removal
        group_before = await duplicate_group_repo.get_group(str(group.id))
        assert group_before.group_size == 2

        # Remove relationship
        await duplicate_group_repo.remove_relationship(relationship.id)

        # Verify group_size was updated by trigger
        group_after = await duplicate_group_repo.get_group(str(group.id))
        assert group_after.group_size == 1

        # Verify relationship is gone
        retrieved_rel = await duplicate_group_repo.get_relationship(relationship.id)
        assert retrieved_rel is None

    async def test_remove_group(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test removing an entire duplicate group."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
        )

        # Remove group (should CASCADE remove relationships)
        await duplicate_group_repo.remove_group(str(group.id))

        # Verify group is gone
        retrieved_group = await duplicate_group_repo.get_group(str(group.id))
        assert retrieved_group is None

        # Verify duplicate page still exists (only relationship removed)
        # (We'd need to check via CrawledPageRepository in real scenario)

    async def test_update_similarity_score(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test updating similarity score for a relationship."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        relationship = await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="fuzzy_match",
            similarity_score=85,
        )

        # Update score
        updated_rel = await duplicate_group_repo.update_similarity_score(relationship.id, 92)

        assert updated_rel.similarity_score == 92
        assert updated_rel.id == relationship.id

    async def test_update_similarity_score_invalid_range(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test that invalid similarity score raises error."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        relationship = await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="fuzzy_match",
            similarity_score=85,
        )

        with pytest.raises(ValueError, match="must be 0-100"):
            await duplicate_group_repo.update_similarity_score(relationship.id, 150)

    async def test_count_by_detection_method(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
        duplicate_page2,
    ) -> None:
        """Test counting duplicates by detection method."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        # Add duplicates with different methods
        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
        )

        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page2.id),
            detection_method="fuzzy_match",
        )

        # Count by method
        counts = await duplicate_group_repo.count_by_detection_method()

        assert len(counts) >= 2
        method_dict = {row.detection_method: row.count for row in counts}
        assert method_dict.get("exact_hash", 0) >= 1
        assert method_dict.get("fuzzy_match", 0) >= 1

    async def test_get_canonical_for_duplicate(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test getting canonical page for a duplicate."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
        )

        # Get canonical for duplicate
        canonical = await duplicate_group_repo.get_canonical_for_duplicate(str(duplicate_page1.id))

        assert canonical is not None
        assert canonical.id == canonical_page.id
        assert canonical.url == canonical_page.url
        assert canonical.content_hash == canonical_page.content_hash

    async def test_list_all_groups(
        self, duplicate_group_repo: DuplicateGroupRepository, canonical_page
    ) -> None:
        """Test listing all duplicate groups with pagination."""
        # Create multiple groups
        group1 = await duplicate_group_repo.create_group(str(canonical_page.id))

        # List groups
        groups = await duplicate_group_repo.list_all_groups(limit=10, offset=0)

        assert len(groups) >= 1
        assert any(g.id == group1.id for g in groups)

    async def test_get_relationship_by_page(
        self,
        duplicate_group_repo: DuplicateGroupRepository,
        canonical_page,
        duplicate_page1,
    ) -> None:
        """Test checking if a page is already in a group."""
        group = await duplicate_group_repo.create_group(str(canonical_page.id))

        # Before adding
        rel_before = await duplicate_group_repo.get_relationship_by_page(
            str(group.id), str(duplicate_page1.id)
        )
        assert rel_before is None

        # Add duplicate
        await duplicate_group_repo.add_duplicate(
            group_id=str(group.id),
            duplicate_page_id=str(duplicate_page1.id),
            detection_method="exact_hash",
        )

        # After adding
        rel_after = await duplicate_group_repo.get_relationship_by_page(
            str(group.id), str(duplicate_page1.id)
        )
        assert rel_after is not None
        assert str(rel_after.duplicate_page_id) == str(duplicate_page1.id)
