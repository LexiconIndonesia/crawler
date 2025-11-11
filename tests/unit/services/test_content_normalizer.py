"""Unit tests for ContentNormalizer service."""

import pytest

from crawler.services.content_normalizer import ContentNormalizer


@pytest.fixture
def normalizer() -> ContentNormalizer:
    """Create ContentNormalizer instance."""
    return ContentNormalizer()


class TestContentNormalizer:
    """Test suite for ContentNormalizer."""

    def test_normalize_basic_html(self, normalizer: ContentNormalizer) -> None:
        """Test basic HTML normalization."""
        html = """
        <html>
            <body>
                <article>
                    <h1>Title</h1>
                    <p>This is the main content.</p>
                </article>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        # Should extract text, normalize whitespace, and lowercase
        assert result == "title this is the main content."
        assert "\n" not in result  # No newlines in single-block mode

    def test_normalize_empty_html_raises_error(self, normalizer: ContentNormalizer) -> None:
        """Test that empty HTML raises ValueError."""
        with pytest.raises(ValueError, match="HTML content cannot be empty"):
            normalizer.normalize("")

    def test_normalize_bytes_input(self, normalizer: ContentNormalizer) -> None:
        """Test normalization with bytes input."""
        html = b"<html><body><p>Content</p></body></html>"
        result = normalizer.normalize(html)

        assert result == "content"

    def test_remove_boilerplate_tags(self, normalizer: ContentNormalizer) -> None:
        """Test removal of navigation, header, footer, etc."""
        html = """
        <html>
            <body>
                <header>Site Header</header>
                <nav>Navigation Menu</nav>
                <main>
                    <p>Main content here</p>
                </main>
                <footer>Site Footer</footer>
                <aside>Sidebar content</aside>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        # Only main content should remain
        assert "main content here" in result
        assert "site header" not in result
        assert "navigation menu" not in result
        assert "site footer" not in result
        assert "sidebar content" not in result

    def test_remove_scripts_and_styles(self, normalizer: ContentNormalizer) -> None:
        """Test removal of script and style tags."""
        html = """
        <html>
            <head>
                <style>body { color: red; }</style>
                <script>console.log('test');</script>
            </head>
            <body>
                <p>Content</p>
                <script>alert('popup');</script>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert result == "content"
        assert "color: red" not in result
        assert "console.log" not in result
        assert "alert" not in result

    def test_remove_ads_by_class(self, normalizer: ContentNormalizer) -> None:
        """Test removal of elements with ad-related classes."""
        html = """
        <html>
            <body>
                <div class="main-content">
                    <p>Real content</p>
                </div>
                <div class="ad-banner">Advertisement</div>
                <div class="sponsored-content">Sponsored</div>
                <div class="promo-box">Promotion</div>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "real content" in result
        assert "advertisement" not in result
        assert "sponsored" not in result
        assert "promotion" not in result

    def test_remove_ads_by_id(self, normalizer: ContentNormalizer) -> None:
        """Test removal of elements with ad-related IDs."""
        html = """
        <html>
            <body>
                <div id="content">Real content</div>
                <div id="ad_slot_1">Ad</div>
                <div id="banner-ad">Banner</div>
                <div id="tracking-pixel">Tracking</div>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "real content" in result
        assert "ad" not in result
        assert "banner" not in result
        assert "tracking" not in result

    def test_remove_cookie_and_gdpr_banners(self, normalizer: ContentNormalizer) -> None:
        """Test removal of cookie consent and GDPR banners."""
        html = """
        <html>
            <body>
                <p>Main content</p>
                <div class="cookie-banner">We use cookies</div>
                <div class="gdpr-consent">Accept GDPR</div>
                <div class="consent-modal">Cookie consent modal</div>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "main content" in result
        assert "cookies" not in result
        assert "gdpr" not in result
        assert "consent" not in result

    def test_remove_social_sharing_buttons(self, normalizer: ContentNormalizer) -> None:
        """Test removal of social sharing buttons."""
        html = """
        <html>
            <body>
                <article>Article content</article>
                <div class="social-share">Share on Facebook</div>
                <div class="share-buttons">Twitter, LinkedIn</div>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "article content" in result
        assert "share" not in result
        assert "facebook" not in result
        assert "twitter" not in result

    def test_remove_html_comments(self, normalizer: ContentNormalizer) -> None:
        """Test removal of HTML comments."""
        html = """
        <html>
            <body>
                <!-- This is a comment -->
                <p>Visible content</p>
                <!-- Another comment -->
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert result == "visible content"
        assert "comment" not in result

    def test_remove_iso_timestamps(self, normalizer: ContentNormalizer) -> None:
        """Test removal of ISO date/time formats."""
        html = """
        <html>
            <body>
                <p>Published on 2024-01-15</p>
                <p>Updated: 2024-01-15 14:30:00</p>
                <p>Timestamp: 2024-01-15T14:30:00Z</p>
                <p>Main content here</p>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "main content here" in result
        assert "2024" not in result
        assert "14:30" not in result
        assert "published on" in result  # Text remains, only date removed

    def test_remove_human_readable_dates(self, normalizer: ContentNormalizer) -> None:
        """Test removal of human-readable date formats."""
        html = """
        <html>
            <body>
                <p>Posted on January 15, 2024</p>
                <p>Updated: Feb 3, 2024</p>
                <p>Article content</p>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "article content" in result
        assert "january" not in result
        assert "2024" not in result

    def test_remove_relative_timestamps(self, normalizer: ContentNormalizer) -> None:
        """Test removal of relative time expressions."""
        html = """
        <html>
            <body>
                <p>Posted 2 hours ago</p>
                <p>Updated 3 days ago</p>
                <p>Published yesterday</p>
                <p>Last updated: 5 minutes ago</p>
                <p>Content here</p>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "content here" in result
        # Relative time expressions should be removed
        assert "hours ago" not in result
        assert "days ago" not in result
        assert "yesterday" not in result
        assert "minutes ago" not in result

    def test_remove_view_counts_and_engagement(self, normalizer: ContentNormalizer) -> None:
        """Test removal of view counts, likes, comments (preserves shares for business text)."""
        html = """
        <html>
            <body>
                <p>Article title</p>
                <span>1.2K views</span>
                <span>500 likes</span>
                <span>75 shares</span>
                <span>123 comments</span>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert "article title" in result
        assert "views" not in result
        assert "likes" not in result
        # "shares" is now preserved to avoid removing business text like "sold 500 shares"
        assert "75 shares" in result
        assert "comments" not in result
        assert "1.2k" not in result

    def test_preserve_business_shares_text(self, normalizer: ContentNormalizer) -> None:
        """Test that business text containing 'shares' is preserved."""
        html = """
        <html>
            <body>
                <article>
                    <p>The company sold 500 shares at market price.</p>
                    <p>Investors purchased 1000 shares in the IPO.</p>
                    <p>The board approved issuing 250,000 shares.</p>
                    <p>Market shares increased by 15%.</p>
                </article>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        # All business references to "shares" should be preserved
        assert "sold 500 shares" in result
        assert "purchased 1000 shares" in result
        assert "issuing 250,000 shares" in result
        assert "market shares increased" in result

    def test_extract_main_content_semantic_tags(self, normalizer: ContentNormalizer) -> None:
        """Test extraction using semantic HTML5 tags."""
        html = """
        <html>
            <body>
                <nav>Navigation</nav>
                <main>
                    <p>This is the main content</p>
                </main>
                <footer>Footer</footer>
            </body>
        </html>
        """

        result = normalizer.normalize(html, extract_main_only=True)

        assert "main content" in result
        # Navigation and footer removed by boilerplate removal

    def test_extract_main_content_article_tag(self, normalizer: ContentNormalizer) -> None:
        """Test extraction using article tag."""
        html = """
        <html>
            <body>
                <div>Other content</div>
                <article>
                    <h1>Article title</h1>
                    <p>Article content</p>
                </article>
            </body>
        </html>
        """

        result = normalizer.normalize(html, extract_main_only=True)

        assert "article title" in result
        assert "article content" in result

    def test_extract_main_content_by_class(self, normalizer: ContentNormalizer) -> None:
        """Test extraction using common content class names."""
        html = """
        <html>
            <body>
                <div class="sidebar">Sidebar</div>
                <div class="main-content">
                    <p>Main content here</p>
                </div>
            </body>
        </html>
        """

        result = normalizer.normalize(html, extract_main_only=True)

        assert "main content here" in result

    def test_extract_main_content_fallback_to_body(self, normalizer: ContentNormalizer) -> None:
        """Test fallback to body when no main content container found."""
        html = """
        <html>
            <body>
                <div>Some content</div>
                <p>More content</p>
            </body>
        </html>
        """

        result = normalizer.normalize(html, extract_main_only=True)

        # Should use body as fallback
        assert "some content" in result
        assert "more content" in result

    def test_preserve_structure_mode(self, normalizer: ContentNormalizer) -> None:
        """Test preservation of paragraph structure."""
        html = """
        <html>
            <body>
                <p>First paragraph</p>
                <p>Second paragraph</p>
                <h2>Heading</h2>
                <p>Third paragraph</p>
            </body>
        </html>
        """

        result = normalizer.normalize(html, preserve_structure=True)

        # Should have newlines between paragraphs
        assert "\n" in result
        assert "first paragraph" in result
        assert "second paragraph" in result
        assert "heading" in result

    def test_normalize_whitespace(self, normalizer: ContentNormalizer) -> None:
        """Test whitespace normalization."""
        html = """
        <html>
            <body>
                <p>Text    with     multiple     spaces</p>
                <p>Text
                with
                newlines</p>
                <p>Text\t\twith\ttabs</p>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        # Multiple spaces/tabs/newlines should become single space
        assert "  " not in result
        assert "\n" not in result
        assert "\t" not in result
        assert "text with multiple spaces" in result
        assert "text with newlines" in result
        assert "text with tabs" in result

    def test_lowercase_conversion(self, normalizer: ContentNormalizer) -> None:
        """Test conversion to lowercase."""
        html = """
        <html>
            <body>
                <p>UPPERCASE and MixedCase Text</p>
            </body>
        </html>
        """

        result = normalizer.normalize(html)

        assert result == "uppercase and mixedcase text"
        assert result.islower()

    def test_normalize_for_hash_convenience_method(self, normalizer: ContentNormalizer) -> None:
        """Test convenience method for hash generation."""
        html = """
        <html>
            <body>
                <nav>Nav</nav>
                <article>
                    <h1>Title</h1>
                    <p>Posted on 2024-01-15</p>
                    <p>Content here</p>
                </article>
                <footer>Footer</footer>
            </body>
        </html>
        """

        result = normalizer.normalize_for_hash(html)

        # Should use optimal settings for hashing
        assert "title" in result
        assert "content here" in result
        assert "nav" not in result
        assert "footer" not in result
        assert "2024" not in result

    def test_complex_real_world_example(self, normalizer: ContentNormalizer) -> None:
        """Test with complex real-world-like HTML."""
        html = """
        <!DOCTYPE html>
        <html>
            <head>
                <title>Article Title</title>
                <script>console.log('analytics');</script>
                <style>body { margin: 0; }</style>
            </head>
            <body>
                <header>
                    <nav>
                        <a href="/">Home</a>
                        <a href="/about">About</a>
                    </nav>
                </header>

                <div class="cookie-banner">We use cookies</div>

                <main>
                    <article>
                        <h1>Breaking News: Important Event</h1>
                        <div class="meta">
                            <span>Published: January 15, 2024</span>
                            <span>Updated 2 hours ago</span>
                            <span>1.5K views</span>
                        </div>

                        <p>This is the main article content that should be preserved.</p>
                        <p>Another paragraph with important information.</p>

                        <div class="ad-slot">Advertisement</div>

                        <p>More content after the ad.</p>

                        <div class="social-share">
                            <button>Share on Facebook</button>
                            <button>Tweet this</button>
                        </div>
                    </article>

                    <aside class="related-articles">
                        <h3>Related Articles</h3>
                        <ul>
                            <li>Article 1</li>
                            <li>Article 2</li>
                        </ul>
                    </aside>
                </main>

                <footer>
                    <p>© 2024 Example Site</p>
                    <div class="newsletter-signup">Subscribe</div>
                </footer>

                <!-- Google Analytics -->
                <script>ga('send', 'pageview');</script>
            </body>
        </html>
        """

        result = normalizer.normalize_for_hash(html)

        # Should contain main content
        assert "breaking news" in result
        assert "important event" in result
        assert "main article content" in result
        assert "important information" in result
        assert "more content after the ad" in result

        # Should NOT contain boilerplate
        assert "home" not in result  # nav
        assert "about" not in result  # nav
        assert "cookies" not in result  # cookie banner
        assert "advertisement" not in result  # ad
        assert "facebook" not in result  # social
        assert "tweet" not in result  # social
        assert "related articles" not in result  # aside
        assert "subscribe" not in result  # footer
        assert "2024" not in result  # copyright year
        assert "console.log" not in result  # script
        assert "analytics" not in result  # script

        # Should NOT contain dynamic content
        assert "january" not in result  # date
        assert "hours ago" not in result  # relative time
        assert "views" not in result  # view count

    def test_identical_content_different_timestamps(self, normalizer: ContentNormalizer) -> None:
        """Test that identical content with different timestamps normalizes to same result."""
        html1 = """
        <html><body>
            <article>
                <p>Published: 2024-01-15</p>
                <p>Main content here</p>
            </article>
        </body></html>
        """

        html2 = """
        <html><body>
            <article>
                <p>Published: 2024-01-20</p>
                <p>Main content here</p>
            </article>
        </body></html>
        """

        result1 = normalizer.normalize_for_hash(html1)
        result2 = normalizer.normalize_for_hash(html2)

        # Should be identical after normalization
        assert result1 == result2
        assert result1 == "published: main content here"

    def test_identical_content_different_view_counts(self, normalizer: ContentNormalizer) -> None:
        """Test that identical content with different view counts normalizes to same result."""
        html1 = "<html><body><article><p>Article</p><span>100 views</span></article></body></html>"
        html2 = "<html><body><article><p>Article</p><span>5000 views</span></article></body></html>"

        result1 = normalizer.normalize_for_hash(html1)
        result2 = normalizer.normalize_for_hash(html2)

        assert result1 == result2
        assert result1 == "article"

    def test_skip_timestamp_removal(self, normalizer: ContentNormalizer) -> None:
        """Test that timestamps can be preserved if needed."""
        html = """
        <html><body>
            <p>Posted on 2024-01-15</p>
            <p>Content</p>
        </body></html>
        """

        result = normalizer.normalize(html, remove_timestamps=False)

        # Timestamps should be preserved
        assert "2024-01-15" in result
        assert "content" in result

    def test_skip_main_content_extraction(self, normalizer: ContentNormalizer) -> None:
        """Test that main content extraction can be skipped."""
        html = """
        <html><body>
            <nav>Navigation</nav>
            <article>Content</article>
        </body></html>
        """

        result = normalizer.normalize(html, extract_main_only=False)

        # Should still remove boilerplate tags (nav, header, footer)
        # but won't isolate to <main> or <article>
        assert "content" in result
