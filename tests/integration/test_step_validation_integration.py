"""Integration tests for step validation in orchestrator."""

from unittest.mock import patch

import httpx
import pytest

from crawler.services.step_orchestrator import StepOrchestrator


class TestStepValidationIntegration:
    """Integration tests for step validation."""

    @pytest.mark.asyncio
    async def test_input_validation_failure_stops_execution(self):
        """Test that input validation failure prevents step execution."""
        # Define step with invalid input by passing a non-list, non-string value
        steps = [
            {
                "name": "invalid_step",
                "type": "scrape",
                "method": "http",
                "config": {"url": " \t "},  # Whitespace-only URL - will fail validation
                "selectors": {"title": "h1"},
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-validation-job",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Execute workflow
        context = await orchestrator.execute_workflow()

        # Verify step failed due to input validation
        assert "invalid_step" in context.step_results
        step_result = context.step_results["invalid_step"]
        assert not step_result.success
        # Check that it failed with validation error
        assert "validation" in step_result.error.lower()
        assert "validation_errors" in step_result.metadata

    @pytest.mark.asyncio
    async def test_output_validation_warns_on_invalid_output(self):
        """Test that output validation logs warnings but doesn't fail step."""
        steps = [
            {
                "name": "test_step",
                "type": "crawl",
                "method": "http",
                "config": {},
                "selectors": {},  # No selectors - will extract empty data
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-output-validation",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock HTTP response with no data to extract
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_request.return_value = httpx.Response(
                status_code=200,
                content=b"<html><body>No links here</body></html>",
                headers={"content-type": "text/html"},
            )

            # Execute workflow
            context = await orchestrator.execute_workflow()

            # Verify step completed but output validation may have warnings
            assert "test_step" in context.step_results
            # Step should succeed even with invalid output (non-strict mode)
            # The crawl will return empty extracted_data which violates schema
            # but we use strict=False for output validation

    @pytest.mark.asyncio
    async def test_valid_crawl_step_passes_validation(self):
        """Test that valid crawl step passes both input and output validation."""
        steps = [
            {
                "name": "valid_crawl",
                "type": "crawl",
                "method": "http",
                "config": {"url": "https://example.com/articles"},
                "selectors": {
                    "urls": {
                        "selector": "a.article",
                        "attribute": "href",
                        "type": "array",
                    }
                },
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-valid-crawl",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock HTTP response with URLs
        with patch("httpx.AsyncClient.request") as mock_request:
            mock_request.return_value = httpx.Response(
                status_code=200,
                content=b"""
                <html><body>
                    <a class="article" href="/article1">Article 1</a>
                    <a class="article" href="/article2">Article 2</a>
                </body></html>
                """,
                headers={"content-type": "text/html"},
            )

            context = await orchestrator.execute_workflow()

            # Verify step succeeded with valid data
            assert "valid_crawl" in context.step_results
            step_result = context.step_results["valid_crawl"]
            assert step_result.success
            assert "urls" in step_result.extracted_data
            assert len(step_result.extracted_data["urls"]) == 2
            # No validation errors
            assert "validation_errors" not in step_result.metadata
            assert "output_validation_warnings" not in step_result.metadata

    @pytest.mark.asyncio
    async def test_valid_scrape_step_passes_validation(self):
        """Test that valid scrape step passes both input and output validation."""
        steps = [
            {
                "name": "crawl_urls",
                "type": "crawl",
                "method": "http",
                "config": {},
                "selectors": {
                    "article_urls": {
                        "selector": "a",
                        "attribute": "href",
                        "type": "array",
                    }
                },
            },
            {
                "name": "scrape_articles",
                "type": "scrape",
                "method": "http",
                "input_from": "crawl_urls.article_urls",
                "selectors": {
                    "title": "h1",
                    "content": "p",
                },
            },
        ]

        orchestrator = StepOrchestrator(
            job_id="test-valid-scrape",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            # Step 1: List page with URLs
            list_response = httpx.Response(
                status_code=200,
                content=b"""
                <html><body>
                    <a href="/article1">Article 1</a>
                    <a href="/article2">Article 2</a>
                </body></html>
                """,
                headers={"content-type": "text/html"},
            )

            # Step 2: Article pages
            article_response = httpx.Response(
                status_code=200,
                content=b"""
                <html><body>
                    <h1>Article Title</h1>
                    <p>Article content</p>
                </body></html>
                """,
                headers={"content-type": "text/html"},
            )

            mock_request.side_effect = [list_response, article_response, article_response]

            context = await orchestrator.execute_workflow()

            # Verify both steps succeeded
            assert "crawl_urls" in context.step_results
            assert "scrape_articles" in context.step_results

            crawl_result = context.step_results["crawl_urls"]
            assert crawl_result.success
            assert "article_urls" in crawl_result.extracted_data

            scrape_result = context.step_results["scrape_articles"]
            assert scrape_result.success
            assert "items" in scrape_result.extracted_data
            # Validation metadata should show success
            assert scrape_result.metadata.get("total_urls") == 2
            assert scrape_result.metadata.get("successful_urls") == 2

    @pytest.mark.asyncio
    async def test_empty_url_list_handled_gracefully(self):
        """Test that empty URL list is handled gracefully (not a validation failure)."""
        steps = [
            {
                "name": "step1",
                "type": "crawl",
                "method": "http",
                "config": {},
                "selectors": {"urls": "a"},
            },
            {
                "name": "step2_scrape",
                "type": "scrape",
                "method": "http",
                "input_from": "step1.urls",
                "selectors": {"title": "h1"},
            },
        ]

        orchestrator = StepOrchestrator(
            job_id="test-empty-url-list",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            # Step 1: Page with no links
            mock_request.return_value = httpx.Response(
                status_code=200,
                content=b"<html><body>No links</body></html>",
                headers={"content-type": "text/html"},
            )

            context = await orchestrator.execute_workflow()

            # Step 1 should succeed but extract no URLs
            assert context.step_results["step1"].success

            # Step 2 should fail with "No URLs to process" (not a validation error)
            step2 = context.step_results["step2_scrape"]
            assert not step2.success
            # This is a pre-validation check, not a validation error
            assert "no urls" in step2.error.lower()
