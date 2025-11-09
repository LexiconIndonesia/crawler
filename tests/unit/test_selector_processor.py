"""Unit tests for selector processor."""

import pytest

from crawler.services.selector_processor import SelectorProcessor


class TestSelectorProcessor:
    """Test suite for SelectorProcessor."""

    @pytest.fixture
    def html_content(self):
        """Sample HTML content for testing."""
        return """
        <html>
            <head><title>Test Page</title></head>
            <body>
                <h1 class="title">Main Title</h1>
                <div class="content">
                    <p>Paragraph 1</p>
                    <p>Paragraph 2</p>
                </div>
                <ul class="links">
                    <li><a href="/link1" class="article">Article 1</a></li>
                    <li><a href="/link2" class="article">Article 2</a></li>
                    <li><a href="/link3" class="article">Article 3</a></li>
                </ul>
            </body>
        </html>
        """

    @pytest.fixture
    def json_content(self):
        """Sample JSON content for testing."""
        return {
            "status": "success",
            "data": {
                "user": {"name": "John", "email": "john@example.com"},
                "posts": [
                    {"title": "Post 1", "url": "/post1"},
                    {"title": "Post 2", "url": "/post2"},
                ],
            },
        }

    def test_process_css_selector_single(self, html_content):
        """Test processing simple CSS selector for single result."""
        processor = SelectorProcessor()
        selectors = {"title": "h1.title"}

        result = processor.process_selectors(html_content, selectors)

        assert result["title"] == "Main Title"

    def test_process_css_selector_array(self, html_content):
        """Test processing CSS selector for array result."""
        processor = SelectorProcessor()
        selectors = {"links": {"selector": "a.article", "attribute": "href", "type": "array"}}

        result = processor.process_selectors(html_content, selectors)

        assert result["links"] == ["/link1", "/link2", "/link3"]

    def test_process_xpath_selector(self, html_content):
        """Test processing XPath selector."""
        processor = SelectorProcessor()
        selectors = {"title": "//h1[@class='title']/text()"}

        result = processor.process_selectors(html_content, selectors)

        assert result["title"] == "Main Title"

    def test_process_multiple_selectors(self, html_content):
        """Test processing multiple selectors at once."""
        processor = SelectorProcessor()
        selectors = {
            "title": "h1.title",
            "paragraphs": {"selector": ".content p", "type": "array"},
            "links": {"selector": "a.article", "attribute": "href", "type": "array"},
        }

        result = processor.process_selectors(html_content, selectors)

        assert result["title"] == "Main Title"
        assert result["paragraphs"] == ["Paragraph 1", "Paragraph 2"]
        assert result["links"] == ["/link1", "/link2", "/link3"]

    def test_process_json_selector_simple(self, json_content):
        """Test processing simple JSON path selector."""
        processor = SelectorProcessor()
        selectors = {"status": "status", "user_name": "data.user.name"}

        result = processor.process_selectors(json_content, selectors)

        assert result["status"] == "success"
        assert result["user_name"] == "John"

    def test_process_json_selector_nested(self, json_content):
        """Test processing nested JSON path selector."""
        processor = SelectorProcessor()
        selectors = {"email": "data.user.email"}

        result = processor.process_selectors(json_content, selectors)

        assert result["email"] == "john@example.com"

    def test_process_json_selector_array_index(self, json_content):
        """Test processing JSON path with array indexing."""
        processor = SelectorProcessor()
        selectors = {
            "first_post": "data.posts.0.title",
            "first_url": "data.posts.0.url",
        }

        result = processor.process_selectors(json_content, selectors)

        assert result["first_post"] == "Post 1"
        assert result["first_url"] == "/post1"

    def test_extract_single_field_html(self, html_content):
        """Test extracting a single field from HTML."""
        processor = SelectorProcessor()

        result = processor.extract_single_field(html_content, "h1.title")

        assert result == "Main Title"

    def test_extract_multiple_fields_html(self, html_content):
        """Test extracting multiple fields from HTML."""
        processor = SelectorProcessor()

        result = processor.extract_multiple_fields(html_content, "a.article", "href")

        assert result == ["/link1", "/link2", "/link3"]

    def test_extract_single_field_json(self, json_content):
        """Test extracting a single field from JSON."""
        processor = SelectorProcessor()

        result = processor.extract_single_field(json_content, "data.user.name")

        assert result == "John"

    def test_detect_xpath_selector(self):
        """Test XPath selector detection."""
        processor = SelectorProcessor()

        assert processor._detect_selector_type("//div[@class='test']") == "xpath"
        assert processor._detect_selector_type("/html/body/div") == "xpath"
        assert processor._detect_selector_type("div.class") == "css"
        assert processor._detect_selector_type("#id-selector") == "css"

    def test_empty_selectors(self, html_content):
        """Test processing with empty selectors."""
        processor = SelectorProcessor()

        result = processor.process_selectors(html_content, {})

        assert result == {}

    def test_selector_not_found(self, html_content):
        """Test behavior when selector doesn't match anything."""
        processor = SelectorProcessor()
        selectors = {"missing": ".nonexistent-class"}

        result = processor.process_selectors(html_content, selectors)

        assert result["missing"] is None

    def test_invalid_selector_config(self, html_content):
        """Test error handling for invalid selector configuration."""
        processor = SelectorProcessor()
        selectors = {"invalid": {"no_selector_field": "value"}}

        result = processor.process_selectors(html_content, selectors)

        # Should return None for invalid config
        assert result["invalid"] is None

    def test_json_path_not_found(self, json_content):
        """Test behavior when JSON path doesn't exist."""
        processor = SelectorProcessor()
        selectors = {"missing": "data.nonexistent.field"}

        result = processor.process_selectors(json_content, selectors)

        assert result["missing"] is None

    def test_extract_attribute_from_html(self, html_content):
        """Test extracting HTML attribute values."""
        processor = SelectorProcessor()
        selectors = {"first_link": {"selector": "a.article", "attribute": "href"}}

        result = processor.process_selectors(html_content, selectors)

        assert result["first_link"] == "/link1"
