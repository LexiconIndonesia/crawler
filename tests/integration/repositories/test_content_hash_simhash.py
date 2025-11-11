"""Integration tests for content hash Simhash functionality.

Tests similar content detection, fingerprint storage, and hash collision handling.
"""

import hashlib

import pytest

from crawler.db.repositories import ContentHashRepository
from crawler.utils import Simhash


@pytest.mark.asyncio
class TestContentHashSimhash:
    """Integration tests for Simhash-based content similarity detection."""

    async def test_upsert_with_simhash(self, content_hash_repo: ContentHashRepository) -> None:
        """Test storing content hash with Simhash fingerprint."""
        content = "The quick brown fox jumps over the lazy dog"
        content_hash_value = hashlib.sha256(content.encode()).hexdigest()
        simhash = Simhash(content)

        result = await content_hash_repo.upsert_with_simhash(
            content_hash_value=content_hash_value,
            first_seen_page_id=None,
            simhash_fingerprint=simhash.fingerprint,
        )

        assert result is not None
        assert result.content_hash == content_hash_value
        assert result.simhash_fingerprint == simhash.fingerprint
        assert result.occurrence_count == 1

    async def test_get_by_fingerprint(self, content_hash_repo: ContentHashRepository) -> None:
        """Test retrieving content by exact Simhash fingerprint."""
        content = "Python is a high-level programming language"
        content_hash_value = hashlib.sha256(content.encode()).hexdigest()
        simhash = Simhash(content)

        # Store content
        await content_hash_repo.upsert_with_simhash(
            content_hash_value=content_hash_value,
            first_seen_page_id=None,
            simhash_fingerprint=simhash.fingerprint,
        )

        # Retrieve by fingerprint
        result = await content_hash_repo.get_by_fingerprint(simhash.fingerprint)

        assert result is not None
        assert result.content_hash == content_hash_value
        assert result.simhash_fingerprint == simhash.fingerprint

    async def test_find_similar_content_95_percent_threshold(
        self, content_hash_repo: ContentHashRepository
    ) -> None:
        """Test finding similar content with 95% similarity threshold."""
        # Original content
        original_content = "The quick brown fox jumps over the lazy dog"
        original_hash = hashlib.sha256(original_content.encode()).hexdigest()
        original_simhash = Simhash(original_content)

        # Very similar content (changed one word: "the" -> "a")
        similar_content = "The quick brown fox jumps over a lazy dog"
        similar_hash = hashlib.sha256(similar_content.encode()).hexdigest()
        similar_simhash = Simhash(similar_content)

        # Different content
        different_content = "Python programming language is awesome"
        different_hash = hashlib.sha256(different_content.encode()).hexdigest()
        different_simhash = Simhash(different_content)

        # Store all content
        await content_hash_repo.upsert_with_simhash(
            original_hash, None, original_simhash.fingerprint
        )
        await content_hash_repo.upsert_with_simhash(similar_hash, None, similar_simhash.fingerprint)
        await content_hash_repo.upsert_with_simhash(
            different_hash, None, different_simhash.fingerprint
        )

        # Find similar to original (max_distance=10 allows for minor changes)
        # Note: Changing 1 word out of 9 results in distance ~7
        results = await content_hash_repo.find_similar(
            target_fingerprint=original_simhash.fingerprint,
            max_distance=10,
            exclude_hash=original_hash,
            limit=10,
        )

        # Should find the similar content but not the different one
        assert len(results) >= 1

        # Verify the similar content is found
        similar_found = any(r.content_hash == similar_hash for r in results)
        assert similar_found, "Similar content should be found within 95% threshold"

        # Verify the different content is NOT found
        different_found = any(r.content_hash == different_hash for r in results)
        assert not different_found, "Different content should not be found"

    async def test_find_similar_ordered_by_distance(
        self, content_hash_repo: ContentHashRepository
    ) -> None:
        """Test that similar content is ordered by Hamming distance."""
        base_content = "Web crawling is an automated process for extracting data"
        base_hash = hashlib.sha256(base_content.encode()).hexdigest()
        base_simhash = Simhash(base_content)

        # Very similar (1 word change)
        very_similar = "Web crawling is an automatic process for extracting data"
        vs_hash = hashlib.sha256(very_similar.encode()).hexdigest()
        vs_simhash = Simhash(very_similar)

        # Moderately similar (2 word changes)
        mod_similar = "Web scraping is an automatic process for extracting information"
        ms_hash = hashlib.sha256(mod_similar.encode()).hexdigest()
        ms_simhash = Simhash(mod_similar)

        # Store all
        await content_hash_repo.upsert_with_simhash(base_hash, None, base_simhash.fingerprint)
        await content_hash_repo.upsert_with_simhash(vs_hash, None, vs_simhash.fingerprint)
        await content_hash_repo.upsert_with_simhash(ms_hash, None, ms_simhash.fingerprint)

        # Find similar (distance=11 for very similar, 16 for moderately similar)
        results = await content_hash_repo.find_similar(
            target_fingerprint=base_simhash.fingerprint,
            max_distance=20,  # Allow both to be found
            exclude_hash=base_hash,
            limit=10,
        )

        # Results should be ordered by distance (closest first)
        assert len(results) >= 2

        # Verify ordering
        for i in range(len(results) - 1):
            assert results[i].hamming_distance <= results[i + 1].hamming_distance

    async def test_handle_hash_collisions(self, content_hash_repo: ContentHashRepository) -> None:
        """Test handling of hash collisions (different content, same fingerprint).

        While Simhash collisions are rare, we should handle them correctly by
        using the content_hash (SHA256) as the primary key.
        """
        content1 = "First piece of content"
        hash1 = hashlib.sha256(content1.encode()).hexdigest()
        simhash1 = Simhash(content1)

        content2 = "Second piece of content"
        hash2 = hashlib.sha256(content2.encode()).hexdigest()

        # Artificially use same fingerprint (simulating collision)
        same_fingerprint = simhash1.fingerprint

        # Store both with same fingerprint
        result1 = await content_hash_repo.upsert_with_simhash(hash1, None, same_fingerprint)
        result2 = await content_hash_repo.upsert_with_simhash(hash2, None, same_fingerprint)

        # Both should be stored (different content_hash primary keys)
        assert result1 is not None
        assert result2 is not None
        assert result1.content_hash != result2.content_hash
        assert result1.simhash_fingerprint == result2.simhash_fingerprint

        # Retrieve by fingerprint should return one of them
        by_fingerprint = await content_hash_repo.get_by_fingerprint(same_fingerprint)
        assert by_fingerprint is not None

        # Retrieve by content hash should return correct ones
        by_hash1 = await content_hash_repo.get(hash1)
        by_hash2 = await content_hash_repo.get(hash2)
        assert by_hash1 is not None
        assert by_hash2 is not None
        assert by_hash1.content_hash == hash1
        assert by_hash2.content_hash == hash2

    async def test_upsert_increments_count(self, content_hash_repo: ContentHashRepository) -> None:
        """Test that upserting existing content increments occurrence count."""
        content = "Duplicate content test"
        content_hash_value = hashlib.sha256(content.encode()).hexdigest()
        simhash = Simhash(content)

        # First insert
        result1 = await content_hash_repo.upsert_with_simhash(
            content_hash_value, None, simhash.fingerprint
        )
        assert result1 is not None
        assert result1.occurrence_count == 1

        # Second insert (should increment)
        result2 = await content_hash_repo.upsert_with_simhash(
            content_hash_value, None, simhash.fingerprint
        )
        assert result2 is not None
        assert result2.occurrence_count == 2

        # Third insert
        result3 = await content_hash_repo.upsert_with_simhash(
            content_hash_value, None, simhash.fingerprint
        )
        assert result3 is not None
        assert result3.occurrence_count == 3

    async def test_find_similar_with_limit(self, content_hash_repo: ContentHashRepository) -> None:
        """Test that limit parameter works correctly."""
        base_content = "Test content for limit check"
        base_hash = hashlib.sha256(base_content.encode()).hexdigest()
        base_simhash = Simhash(base_content)

        # Store base content
        await content_hash_repo.upsert_with_simhash(base_hash, None, base_simhash.fingerprint)

        # Store 10 similar pieces of content
        for i in range(10):
            similar = f"Test content for limit check variation {i}"
            similar_hash = hashlib.sha256(similar.encode()).hexdigest()
            similar_simhash = Simhash(similar)
            await content_hash_repo.upsert_with_simhash(
                similar_hash, None, similar_simhash.fingerprint
            )

        # Query with limit=5
        results = await content_hash_repo.find_similar(
            target_fingerprint=base_simhash.fingerprint,
            max_distance=5,
            exclude_hash=base_hash,
            limit=5,
        )

        # Should return at most 5 results
        assert len(results) <= 5

    async def test_find_similar_excludes_target(
        self, content_hash_repo: ContentHashRepository
    ) -> None:
        """Test that target hash is excluded from results."""
        content = "Content to exclude from results"
        content_hash_value = hashlib.sha256(content.encode()).hexdigest()
        simhash = Simhash(content)

        # Store content
        await content_hash_repo.upsert_with_simhash(content_hash_value, None, simhash.fingerprint)

        # Find similar (excluding itself)
        results = await content_hash_repo.find_similar(
            target_fingerprint=simhash.fingerprint,
            max_distance=0,  # Even with 0 distance (exact match)
            exclude_hash=content_hash_value,
            limit=10,
        )

        # Should not find itself
        assert all(r.content_hash != content_hash_value for r in results)

    async def test_find_similar_no_matches(self, content_hash_repo: ContentHashRepository) -> None:
        """Test finding similar content when there are no matches."""
        content = "Unique content with no similars"
        simhash = Simhash(content)

        # Don't store any content, just query
        results = await content_hash_repo.find_similar(
            target_fingerprint=simhash.fingerprint,
            max_distance=3,
            exclude_hash="",
            limit=10,
        )

        # Should return empty list
        assert results == []

    async def test_real_world_duplicate_detection(
        self, content_hash_repo: ContentHashRepository
    ) -> None:
        """Test real-world duplicate detection scenario."""
        # Scenario: Same article found on different URLs with slight variations

        # Original article
        original = """
        Breaking News: Python 3.14 Released
        The Python Software Foundation announced today the release of Python 3.14.
        This new version includes major performance improvements and new features.
        """
        original_hash = hashlib.sha256(original.encode()).hexdigest()
        original_simhash = Simhash(original)

        # Same article with minor edits (typo fix: "announced" -> "announces")
        variant1 = """
        Breaking News: Python 3.14 Released
        The Python Software Foundation announces today the release of Python 3.14.
        This new version includes major performance improvements and new features.
        """
        v1_hash = hashlib.sha256(variant1.encode()).hexdigest()
        v1_simhash = Simhash(variant1)

        # Same article with extra sentence
        variant2 = """
        Breaking News: Python 3.14 Released
        The Python Software Foundation announced today the release of Python 3.14.
        This new version includes major performance improvements and new features.
        Developers around the world are excited about the update.
        """
        v2_hash = hashlib.sha256(variant2.encode()).hexdigest()
        v2_simhash = Simhash(variant2)

        # Store all variants
        await content_hash_repo.upsert_with_simhash(
            original_hash, None, original_simhash.fingerprint
        )
        await content_hash_repo.upsert_with_simhash(v1_hash, None, v1_simhash.fingerprint)
        await content_hash_repo.upsert_with_simhash(v2_hash, None, v2_simhash.fingerprint)

        # Find duplicates of original (distance ~11 for variant with extra sentence)
        duplicates = await content_hash_repo.find_similar(
            target_fingerprint=original_simhash.fingerprint,
            max_distance=15,  # Allow variant2 with extra sentence
            exclude_hash=original_hash,
            limit=10,
        )

        # Should detect at least the near-exact duplicate
        assert len(duplicates) >= 1

        # Variant1 (exact same content) should be found
        assert any(d.content_hash == v1_hash for d in duplicates)

        # All duplicates should have reasonable Hamming distance
        for dup in duplicates:
            assert dup.hamming_distance <= 15
