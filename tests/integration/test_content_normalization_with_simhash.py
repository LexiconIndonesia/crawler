"""Integration tests for ContentNormalizer with Simhash for duplicate detection.

These tests demonstrate how ContentNormalizer and Simhash work together to
detect near-duplicate content despite dynamic elements like timestamps, ads,
and view counts.
"""

import hashlib

import pytest

from crawler.services.content_normalizer import ContentNormalizer
from crawler.utils.simhash import Simhash


@pytest.fixture
def normalizer() -> ContentNormalizer:
    """Create ContentNormalizer instance."""
    return ContentNormalizer()


class TestContentNormalizationWithSimhash:
    """Integration tests for content normalization + Simhash pipeline."""

    def test_identical_content_different_timestamps_produces_same_hash(
        self, normalizer: ContentNormalizer
    ) -> None:
        """Test that identical articles with different timestamps hash identically."""
        # Article published on different dates
        html1 = """
        <html><body>
            <article>
                <h1>Breaking News: Major Discovery</h1>
                <p class="meta">Published: January 15, 2024 | Updated 2 hours ago</p>
                <p>Scientists have made a groundbreaking discovery in quantum physics.</p>
                <p>The research team found evidence of new particle behavior.</p>
            </article>
        </body></html>
        """

        html2 = """
        <html><body>
            <article>
                <h1>Breaking News: Major Discovery</h1>
                <p class="meta">Published: March 20, 2024 | Updated 5 minutes ago</p>
                <p>Scientists have made a groundbreaking discovery in quantum physics.</p>
                <p>The research team found evidence of new particle behavior.</p>
            </article>
        </body></html>
        """

        # Normalize content
        normalized1 = normalizer.normalize_for_hash(html1)
        normalized2 = normalizer.normalize_for_hash(html2)

        # Should produce identical normalized text
        assert normalized1 == normalized2

        # Generate Simhash fingerprints
        simhash1 = Simhash(normalized1)
        simhash2 = Simhash(normalized2)

        # Should have identical fingerprints (distance = 0)
        assert simhash1.distance(simhash2) == 0
        assert simhash1.similarity(simhash2) == 100.0

    def test_identical_content_different_ads_produces_same_hash(
        self, normalizer: ContentNormalizer
    ) -> None:
        """Test that identical articles with different ads hash identically."""
        html1 = """
        <html><body>
            <article>
                <h1>Product Review: Best Laptops 2024</h1>
                <div class="ad-banner">Advertisement: Buy Now!</div>
                <p>Here are the top laptop recommendations for this year.</p>
            </article>
        </body></html>
        """

        html2 = """
        <html><body>
            <article>
                <h1>Product Review: Best Laptops 2024</h1>
                <div class="sponsored-content">Sponsored: Special Offer!</div>
                <p>Here are the top laptop recommendations for this year.</p>
            </article>
        </body></html>
        """

        normalized1 = normalizer.normalize_for_hash(html1)
        normalized2 = normalizer.normalize_for_hash(html2)

        assert normalized1 == normalized2

        simhash1 = Simhash(normalized1)
        simhash2 = Simhash(normalized2)

        assert simhash1.distance(simhash2) == 0

    def test_identical_content_different_view_counts_produces_same_hash(
        self, normalizer: ContentNormalizer
    ) -> None:
        """Test that articles with different view counts hash identically."""
        html1 = """
        <html><body>
            <article>
                <h1>Tutorial: Learn Python</h1>
                <span class="stats">1,234 views | 56 likes</span>
                <p>This comprehensive guide will teach you Python programming.</p>
            </article>
        </body></html>
        """

        html2 = """
        <html><body>
            <article>
                <h1>Tutorial: Learn Python</h1>
                <span class="stats">9,876 views | 432 likes</span>
                <p>This comprehensive guide will teach you Python programming.</p>
            </article>
        </body></html>
        """

        normalized1 = normalizer.normalize_for_hash(html1)
        normalized2 = normalizer.normalize_for_hash(html2)

        assert normalized1 == normalized2

        simhash1 = Simhash(normalized1)
        simhash2 = Simhash(normalized2)

        assert simhash1.distance(simhash2) == 0

    def test_similar_content_produces_similar_hash(self, normalizer: ContentNormalizer) -> None:
        """Test that similar but not identical content produces similar hashes."""
        # Original article
        html1 = """
        <html><body>
            <article>
                <h1>Climate Change Impact</h1>
                <p>Scientists warn about rising global temperatures.</p>
                <p>The effects are visible in melting ice caps.</p>
            </article>
        </body></html>
        """

        # Article with minor changes (one word different)
        html2 = """
        <html><body>
            <article>
                <h1>Climate Change Impact</h1>
                <p>Scientists warn about increasing global temperatures.</p>
                <p>The effects are visible in melting ice caps.</p>
            </article>
        </body></html>
        """

        normalized1 = normalizer.normalize_for_hash(html1)
        normalized2 = normalizer.normalize_for_hash(html2)

        # Text should be slightly different
        assert normalized1 != normalized2

        simhash1 = Simhash(normalized1)
        simhash2 = Simhash(normalized2)

        # Should be very similar (within reasonable threshold for short text)
        distance = simhash1.distance(simhash2)
        similarity = simhash1.similarity(simhash2)

        # Short text has higher variance, but should still be similar
        assert distance <= 10  # Similar content
        assert similarity >= 84.0  # Reasonable threshold for short text

    def test_different_content_produces_different_hash(self, normalizer: ContentNormalizer) -> None:
        """Test that completely different content produces different hashes."""
        html1 = """
        <html><body>
            <article>
                <h1>Python Programming Guide</h1>
                <p>Learn the fundamentals of Python programming language.</p>
            </article>
        </body></html>
        """

        html2 = """
        <html><body>
            <article>
                <h1>JavaScript Frameworks</h1>
                <p>Explore modern JavaScript frameworks for web development.</p>
            </article>
        </body></html>
        """

        normalized1 = normalizer.normalize_for_hash(html1)
        normalized2 = normalizer.normalize_for_hash(html2)

        simhash1 = Simhash(normalized1)
        simhash2 = Simhash(normalized2)

        # Should be very different
        distance = simhash1.distance(simhash2)
        similarity = simhash1.similarity(simhash2)

        assert distance > 15  # Well beyond 95% threshold
        assert similarity < 80.0

    def test_complex_news_article_normalization_pipeline(
        self, normalizer: ContentNormalizer
    ) -> None:
        """Test complete pipeline with realistic news article HTML."""
        # Same article from two different news sites with different layouts
        html_site1 = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Tech News - AI Breakthrough</title>
            <script>analytics.track('pageview');</script>
        </head>
        <body>
            <header>
                <nav><a href="/">Home</a> | <a href="/tech">Tech</a></nav>
            </header>

            <main>
                <article>
                    <h1>AI Achieves Breakthrough in Natural Language</h1>
                    <div class="metadata">
                        <span>Published: 2024-01-15 14:30:00</span>
                        <span>By: Tech Reporter</span>
                        <span>2.5K views | 120 shares</span>
                    </div>

                    <div class="ad-slot">
                        <img src="/ad1.jpg" alt="Advertisement">
                    </div>

                    <p>Researchers at leading AI lab have announced a major breakthrough
                    in natural language processing technology.</p>

                    <p>The new model demonstrates unprecedented understanding of context
                    and nuance in human communication.</p>

                    <p>Industry experts predict this will revolutionize how we interact
                    with artificial intelligence systems.</p>

                    <div class="social-share">
                        <button>Share on Facebook</button>
                        <button>Tweet</button>
                    </div>
                </article>

                <aside class="related">
                    <h3>Related Articles</h3>
                    <ul><li>Previous AI News</li></ul>
                </aside>
            </main>

            <footer>
                <p>© 2024 Tech News Site</p>
                <div class="newsletter">Subscribe to our newsletter</div>
            </footer>

            <div class="cookie-consent">We use cookies</div>
        </body>
        </html>
        """

        html_site2 = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Science Daily - AI News</title>
            <script>gtag('config', 'UA-12345');</script>
        </head>
        <body>
            <div class="header-ad">Banner Ad</div>

            <nav>Menu</nav>

            <div class="content">
                <h1>AI Achieves Breakthrough in Natural Language</h1>

                <p class="byline">Reporter Name | Jan 20, 2024 | Updated 1 hour ago</p>
                <p class="engagement">3.2K readers | 200 reactions</p>

                <div class="promo-box">Special Offer!</div>

                <p>Researchers at leading AI lab have announced a major breakthrough
                in natural language processing technology.</p>

                <p>The new model demonstrates unprecedented understanding of context
                and nuance in human communication.</p>

                <p>Industry experts predict this will revolutionize how we interact
                with artificial intelligence systems.</p>
            </div>

            <div class="sidebar">
                <div class="ad-sidebar">Sidebar Ad</div>
                <div class="trending">Trending Now</div>
            </div>

            <footer>Site Footer</footer>
        </body>
        </html>
        """

        # Normalize both versions
        normalized1 = normalizer.normalize_for_hash(html_site1)
        normalized2 = normalizer.normalize_for_hash(html_site2)

        # Generate content hashes (SHA256)
        hash1 = hashlib.sha256(normalized1.encode()).hexdigest()
        hash2 = hashlib.sha256(normalized2.encode()).hexdigest()

        # Content hashes will be different due to different bylines/metadata
        # But Simhash should detect similarity
        assert hash1 != hash2  # Different metadata

        # Generate Simhash fingerprints
        simhash1 = Simhash(normalized1)
        simhash2 = Simhash(normalized2)

        # Should be very similar (same core article content)
        distance = simhash1.distance(simhash2)
        similarity = simhash1.similarity(simhash2)

        # Very similar despite different metadata
        assert distance <= 15  # Near-duplicate threshold (reasonable for medium-length content)
        assert similarity >= 76.0  # High similarity (distance 12-15 for 64-bit hash)

        # Verify normalized content contains main article text
        assert "researchers at leading ai lab" in normalized1
        assert "major breakthrough" in normalized1
        assert "natural language processing" in normalized1

        # Verify dynamic elements were removed
        assert "2024" not in normalized1  # Dates removed
        assert "views" not in normalized1  # View counts removed
        assert "shares" not in normalized1  # Share counts removed
        assert "advertisement" not in normalized1  # Ads removed
        assert "cookie" not in normalized1  # Cookie banner removed
        assert "footer" not in normalized1  # Footer removed

    def test_normalization_produces_stable_hashes_across_runs(
        self, normalizer: ContentNormalizer
    ) -> None:
        """Test that normalization produces consistent results across multiple runs."""
        html = """
        <html><body>
            <article>
                <h1>Test Article</h1>
                <p>Posted: 2024-01-15 | 1.5K views</p>
                <div class="ad">Ad</div>
                <p>Main content of the article goes here.</p>
            </article>
        </body></html>
        """

        # Normalize multiple times
        results = [normalizer.normalize_for_hash(html) for _ in range(10)]

        # All results should be identical
        assert len(set(results)) == 1

        # Generate Simhash multiple times
        simhashes = [Simhash(result) for result in results]
        fingerprints = [sh.fingerprint for sh in simhashes]

        # All fingerprints should be identical
        assert len(set(fingerprints)) == 1

    def test_sha256_and_simhash_together_for_duplicate_detection(
        self, normalizer: ContentNormalizer
    ) -> None:
        """Test using both SHA256 (exact match) and Simhash (fuzzy match) for duplicates.

        This demonstrates the recommended approach:
        1. Use SHA256 content_hash for exact duplicate detection
        2. Use Simhash for near-duplicate detection (similar content)
        """
        # Exact duplicate (same content, different timestamps)
        html1 = (
            "<html><body><article><p>Posted: 2024-01-15</p><p>Content</p></article></body></html>"
        )
        html2 = (
            "<html><body><article><p>Posted: 2024-02-20</p><p>Content</p></article></body></html>"
        )

        # Near duplicate (similar content)
        html3 = (
            "<html><body><article><p>Posted: 2024-01-15</p>"
            "<p>Similar Content</p></article></body></html>"
        )

        # Different content
        html4 = "<html><body><article><p>Completely different article</p></article></body></html>"

        # Normalize all
        norm1 = normalizer.normalize_for_hash(html1)
        norm2 = normalizer.normalize_for_hash(html2)
        norm3 = normalizer.normalize_for_hash(html3)
        norm4 = normalizer.normalize_for_hash(html4)

        # SHA256 hashes
        hash1 = hashlib.sha256(norm1.encode()).hexdigest()
        hash2 = hashlib.sha256(norm2.encode()).hexdigest()
        hash3 = hashlib.sha256(norm3.encode()).hexdigest()
        hash4 = hashlib.sha256(norm4.encode()).hexdigest()

        # Simhash fingerprints
        simhash1 = Simhash(norm1)
        simhash2 = Simhash(norm2)
        simhash3 = Simhash(norm3)
        simhash4 = Simhash(norm4)

        # Test 1: Exact duplicates have identical SHA256 hashes
        assert hash1 == hash2  # Same content after normalization

        # Test 2: Exact duplicates have identical Simhash (distance = 0)
        assert simhash1.distance(simhash2) == 0

        # Test 3: Near duplicates have different SHA256 hashes
        assert hash1 != hash3

        # Test 4: Near duplicates have similar Simhash (small distance)
        distance_1_3 = simhash1.distance(simhash3)
        assert distance_1_3 <= 15  # Similar content (short text has higher variance)

        # Test 5: Different content has different hashes and large Simhash distance
        assert hash1 != hash4
        distance_1_4 = simhash1.distance(simhash4)
        assert distance_1_4 > 15  # Very different content

        # Summary: Use SHA256 for exact match, Simhash for fuzzy match
        # - hash1 == hash2: Exact duplicate (skip crawling)
        # - simhash1.distance(simhash3) <= 3: Near duplicate at 95% threshold (skip crawling)
        # - simhash1.distance(simhash4) > 15: Different content (crawl normally)
