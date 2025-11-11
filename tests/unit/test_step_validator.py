"""Unit tests for step input/output validation."""

import pytest
from pydantic import ValidationError

from crawler.services.step_validator import (
    CrawlStepInput,
    CrawlStepOutput,
    ScrapeStepInput,
    ScrapeStepOutput,
    StepValidationError,
    StepValidator,
)


class TestCrawlStepInput:
    """Test suite for CrawlStepInput validation."""

    def test_valid_string_url(self):
        """Test validation with valid string URL."""
        input_data = CrawlStepInput(url="https://example.com")
        assert input_data.url == "https://example.com"
        assert input_data.seed_url == "https://example.com"

    def test_valid_list_url(self):
        """Test validation with valid list of URLs."""
        input_data = CrawlStepInput(url=["https://example.com", "https://other.com"])
        assert input_data.url == ["https://example.com", "https://other.com"]
        assert input_data.seed_url == "https://example.com"

    def test_single_url_in_list(self):
        """Test validation with single URL in list."""
        input_data = CrawlStepInput(url=["https://example.com"])
        assert input_data.seed_url == "https://example.com"

    def test_empty_string_url_fails(self):
        """Test that empty string URL fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CrawlStepInput(url="")
        assert "cannot be empty string" in str(exc_info.value)

    def test_empty_list_fails(self):
        """Test that empty list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CrawlStepInput(url=[])
        assert "cannot be empty" in str(exc_info.value)

    def test_empty_first_url_in_list_fails(self):
        """Test that empty first URL in list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CrawlStepInput(url=["", "https://example.com"])
        assert "cannot be empty string" in str(exc_info.value)

    def test_whitespace_only_url_fails(self):
        """Test that whitespace-only URL fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CrawlStepInput(url="   ")
        assert "cannot be empty string" in str(exc_info.value)


class TestScrapeStepInput:
    """Test suite for ScrapeStepInput validation."""

    def test_valid_string_url(self):
        """Test validation with valid string URL."""
        input_data = ScrapeStepInput(urls="https://example.com")
        assert input_data.urls == "https://example.com"
        assert input_data.url_list == ["https://example.com"]

    def test_valid_list_urls(self):
        """Test validation with valid list of URLs."""
        urls = ["https://example.com/1", "https://example.com/2"]
        input_data = ScrapeStepInput(urls=urls)
        assert input_data.urls == urls
        assert input_data.url_list == urls

    def test_empty_string_url_fails(self):
        """Test that empty string URL fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ScrapeStepInput(urls="")
        assert "cannot be empty string" in str(exc_info.value)

    def test_empty_list_fails(self):
        """Test that empty list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ScrapeStepInput(urls=[])
        assert "cannot be empty" in str(exc_info.value)

    def test_non_string_in_list_fails(self):
        """Test that non-string in list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ScrapeStepInput(urls=["https://example.com", 123, "https://other.com"])
        assert "string" in str(exc_info.value).lower()

    def test_empty_url_in_list_fails(self):
        """Test that empty URL in list fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ScrapeStepInput(urls=["https://example.com", "", "https://other.com"])
        assert "cannot be empty string" in str(exc_info.value)


class TestCrawlStepOutput:
    """Test suite for CrawlStepOutput validation."""

    def test_valid_output_with_urls(self):
        """Test validation with valid extracted URLs."""
        output = CrawlStepOutput(
            extracted_data={"urls": ["https://example.com/1", "https://example.com/2"]},
            metadata={"pages_crawled": 1, "total_urls": 2},
        )
        assert "urls" in output.extracted_data
        assert len(output.extracted_data["urls"]) == 2

    def test_valid_output_with_multiple_fields(self):
        """Test validation with multiple extracted fields."""
        output = CrawlStepOutput(
            extracted_data={
                "urls": ["https://example.com/1"],
                "titles": ["Title 1"],
            },
            metadata={"pages_crawled": 1},
        )
        assert len(output.extracted_data) == 2

    def test_empty_extracted_data_fails(self):
        """Test that empty extracted data fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            CrawlStepOutput(
                extracted_data={},
                metadata={},
            )
        assert "must extract at least one field" in str(exc_info.value)

    def test_metadata_defaults_to_empty_dict(self):
        """Test that metadata defaults to empty dict."""
        output = CrawlStepOutput(extracted_data={"urls": []})
        assert output.metadata == {}


class TestScrapeStepOutput:
    """Test suite for ScrapeStepOutput validation."""

    def test_valid_single_url_output(self):
        """Test validation with single URL scrape output."""
        output = ScrapeStepOutput(
            extracted_data={"title": "Article Title", "content": "Article content"},
            metadata={"total_urls": 1, "successful_urls": 1, "failed_urls": 0},
        )
        assert "title" in output.extracted_data
        assert output.metadata["total_urls"] == 1

    def test_valid_multi_url_output(self):
        """Test validation with multiple URL scrape output."""
        output = ScrapeStepOutput(
            extracted_data={
                "items": [
                    {"title": "Article 1"},
                    {"title": "Article 2"},
                ]
            },
            metadata={"total_urls": 2, "successful_urls": 2, "failed_urls": 0},
        )
        assert "items" in output.extracted_data
        assert len(output.extracted_data["items"]) == 2

    def test_empty_items_list_valid(self):
        """Test that empty items list is valid (all URLs failed)."""
        output = ScrapeStepOutput(
            extracted_data={"items": []},
            metadata={"total_urls": 5, "successful_urls": 0, "failed_urls": 5},
        )
        assert output.extracted_data["items"] == []

    def test_items_must_be_list(self):
        """Test that items field must be a list."""
        with pytest.raises(ValidationError) as exc_info:
            ScrapeStepOutput(
                extracted_data={"items": "not a list"},
                metadata={},
            )
        assert "must be a list" in str(exc_info.value)

    def test_metadata_statistics_validation(self):
        """Test metadata statistics validation."""
        output = ScrapeStepOutput(
            extracted_data={"title": "Test"},
            metadata={
                "total_urls": 10,
                "successful_urls": 8,
                "failed_urls": 2,
            },
        )
        assert output.metadata["total_urls"] == 10
        assert output.metadata["successful_urls"] == 8
        assert output.metadata["failed_urls"] == 2

    def test_negative_metadata_count_fails(self):
        """Test that negative count in metadata fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ScrapeStepOutput(
                extracted_data={"title": "Test"},
                metadata={
                    "total_urls": -1,
                    "successful_urls": 5,
                    "failed_urls": 0,
                },
            )
        assert "non-negative integer" in str(exc_info.value)

    def test_non_integer_metadata_count_fails(self):
        """Test that non-integer count in metadata fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ScrapeStepOutput(
                extracted_data={"title": "Test"},
                metadata={
                    "total_urls": "10",
                    "successful_urls": 5,
                    "failed_urls": 0,
                },
            )
        assert "non-negative integer" in str(exc_info.value)

    def test_metadata_without_statistics_valid(self):
        """Test that metadata without statistics is valid."""
        output = ScrapeStepOutput(
            extracted_data={"title": "Test"},
            metadata={"other_field": "value"},
        )
        assert "other_field" in output.metadata


class TestStepValidator:
    """Test suite for StepValidator."""

    def test_validate_crawl_input_success(self):
        """Test successful crawl input validation."""
        validator = StepValidator()
        result = validator.validate_input(
            step_name="test_step",
            step_type="crawl",
            input_data="https://example.com",
        )
        assert result["url"] == "https://example.com"

    def test_validate_scrape_input_success(self):
        """Test successful scrape input validation."""
        validator = StepValidator()
        result = validator.validate_input(
            step_name="test_step",
            step_type="scrape",
            input_data=["https://example.com/1", "https://example.com/2"],
        )
        assert len(result["urls"]) == 2

    def test_validate_crawl_input_failure_strict(self):
        """Test crawl input validation failure in strict mode."""
        validator = StepValidator()
        with pytest.raises(StepValidationError) as exc_info:
            validator.validate_input(
                step_name="test_step",
                step_type="crawl",
                input_data="",
                strict=True,
            )
        assert exc_info.value.step_name == "test_step"
        assert exc_info.value.validation_type == "input"
        assert len(exc_info.value.errors) > 0

    def test_validate_scrape_input_failure_non_strict(self):
        """Test scrape input validation failure in non-strict mode."""
        validator = StepValidator()
        # Should not raise, just log warning
        result = validator.validate_input(
            step_name="test_step",
            step_type="scrape",
            input_data=[],
            strict=False,
        )
        # Returns original data despite validation failure
        assert "urls" in result

    def test_validate_crawl_output_success(self):
        """Test successful crawl output validation."""
        validator = StepValidator()
        result = validator.validate_output(
            step_name="test_step",
            step_type="crawl",
            extracted_data={"urls": ["https://example.com/1"]},
            metadata={"pages_crawled": 1},
        )
        assert "extracted_data" in result
        assert "urls" in result["extracted_data"]

    def test_validate_scrape_output_success(self):
        """Test successful scrape output validation."""
        validator = StepValidator()
        result = validator.validate_output(
            step_name="test_step",
            step_type="scrape",
            extracted_data={"items": [{"title": "Test"}]},
            metadata={"total_urls": 1, "successful_urls": 1, "failed_urls": 0},
        )
        assert "extracted_data" in result

    def test_validate_output_failure_strict(self):
        """Test output validation failure in strict mode."""
        validator = StepValidator()
        with pytest.raises(StepValidationError) as exc_info:
            validator.validate_output(
                step_name="test_step",
                step_type="crawl",
                extracted_data={},  # Empty - should fail
                metadata={},
                strict=True,
            )
        assert exc_info.value.step_name == "test_step"
        assert exc_info.value.validation_type == "output"

    def test_validate_output_failure_non_strict(self):
        """Test output validation failure in non-strict mode."""
        validator = StepValidator()
        # Should not raise, just log warning
        result = validator.validate_output(
            step_name="test_step",
            step_type="crawl",
            extracted_data={},
            metadata={},
            strict=False,
        )
        # Returns original data despite validation failure
        assert result["extracted_data"] == {}

    def test_validate_unsupported_step_type_input(self):
        """Test validation with unsupported step type (input)."""
        validator = StepValidator()
        result = validator.validate_input(
            step_name="test_step",
            step_type="unknown",
            input_data="https://example.com",
        )
        # Should skip validation and return wrapped data (defaults to scrape format)
        assert "urls" in result

    def test_validate_unsupported_step_type_output(self):
        """Test validation with unsupported step type (output)."""
        validator = StepValidator()
        result = validator.validate_output(
            step_name="test_step",
            step_type="unknown",
            extracted_data={"data": "value"},
            metadata={},
        )
        # Should skip validation and return original data
        assert result["extracted_data"] == {"data": "value"}

    def test_validate_required_fields_present(self):
        """Test required fields validation when all present."""
        validator = StepValidator()
        missing = validator.validate_required_fields(
            step_name="test_step",
            step_type="crawl",
            extracted_data={"urls": [], "titles": []},
            required_fields=["urls", "titles"],
        )
        assert missing == []

    def test_validate_required_fields_missing(self):
        """Test required fields validation when some missing."""
        validator = StepValidator()
        missing = validator.validate_required_fields(
            step_name="test_step",
            step_type="scrape",
            extracted_data={"title": "Test"},
            required_fields=["title", "content", "author"],
        )
        assert "content" in missing
        assert "author" in missing
        assert "title" not in missing

    def test_validation_error_string_representation(self):
        """Test StepValidationError string representation."""
        error = StepValidationError(
            step_name="test_step",
            errors=["Error 1", "Error 2"],
            validation_type="input",
        )
        error_str = str(error)
        assert "test_step" in error_str
        assert "input validation failed" in error_str
        assert "Error 1" in error_str
        assert "Error 2" in error_str
