"""Integration tests for step orchestrator."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from crawler.services.step_orchestrator import StepOrchestrator


class TestStepOrchestrator:
    """Test suite for StepOrchestrator integration."""

    @pytest.mark.asyncio
    async def test_multi_step_workflow_with_data_passing(self):
        """Test multi-step workflow where step 2 uses data from step 1."""
        # Define a 2-step workflow:
        # Step 1: Fetch list page and extract article URLs
        # Step 2: Fetch each article (using URLs from step 1)
        steps = [
            {
                "name": "fetch_list",
                "method": "http",
                "type": "crawl",
                "config": {"url": "https://example.com/articles"},
                "selectors": {
                    "article_urls": {
                        "selector": "a.article-link",
                        "attribute": "href",
                        "type": "array",
                    }
                },
            },
            {
                "name": "fetch_articles",
                "method": "http",
                "type": "scrape",
                "input_from": "fetch_list.article_urls",  # Uses output from step 1
                "selectors": {
                    "title": "h1.title",
                    "content": ".article-body",
                },
            },
        ]

        orchestrator = StepOrchestrator(
            job_id="test-job-1",
            website_id="test-site-1",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock HTTP responses
        with patch("httpx.AsyncClient.request") as mock_request:
            # Step 1: List page with article links
            list_response = AsyncMock()
            list_response.status_code = 200
            list_response.text = """
                <html>
                    <body>
                        <a class="article-link" href="/article1">Article 1</a>
                        <a class="article-link" href="/article2">Article 2</a>
                        <a class="article-link" href="/article3">Article 3</a>
                    </body>
                </html>
            """
            list_response.headers = {"content-type": "text/html"}

            # Step 2: Article pages
            article_response = AsyncMock()
            article_response.status_code = 200
            article_response.text = """
                <html>
                    <body>
                        <h1 class="title">Article Title</h1>
                        <div class="article-body">Article content here</div>
                    </body>
                </html>
            """
            article_response.headers = {"content-type": "text/html"}

            # Return list response first, then article responses
            mock_request.side_effect = [
                list_response,
                article_response,
                article_response,
                article_response,
            ]

            # Execute workflow
            context = await orchestrator.execute_workflow()

            # Verify step 1 completed successfully
            assert "fetch_list" in context.step_results
            step1 = context.step_results["fetch_list"]
            assert step1.success
            assert "article_urls" in step1.extracted_data
            assert len(step1.extracted_data["article_urls"]) == 3

            # Verify step 2 completed successfully
            assert "fetch_articles" in context.step_results
            step2 = context.step_results["fetch_articles"]
            assert step2.success
            # Step 2 should have processed all 3 URLs
            assert step2.metadata["total_urls"] == 3
            assert step2.metadata["successful_urls"] == 3

            # Verify all articles were extracted
            assert "items" in step2.extracted_data
            assert len(step2.extracted_data["items"]) == 3
            # Each item should have title and content
            for item in step2.extracted_data["items"]:
                assert "title" in item
                assert "content" in item

    @pytest.mark.asyncio
    async def test_single_url_workflow_preserves_structure(self):
        """Test that single URL results are not wrapped in 'items' array."""
        steps = [
            {
                "name": "fetch_page",
                "method": "http",
                "type": "scrape",
                "config": {"url": "https://example.com/page"},
                "selectors": {
                    "title": "h1",
                    "content": ".content",
                },
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-job-2",
            website_id="test-site-2",
            base_url="https://example.com",
            steps=steps,
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = """
                <html>
                    <h1>Page Title</h1>
                    <div class="content">Page content</div>
                </html>
            """
            mock_response.headers = {"content-type": "text/html"}
            mock_request.return_value = mock_response

            context = await orchestrator.execute_workflow()

            # Single URL should not have 'items' wrapper
            step_result = context.step_results["fetch_page"]
            assert step_result.success
            assert "title" in step_result.extracted_data
            assert "content" in step_result.extracted_data
            assert "items" not in step_result.extracted_data
            assert step_result.extracted_data["title"] == "Page Title"

    @pytest.mark.asyncio
    async def test_condition_based_step_skipping(self):
        """Test that steps can be skipped based on conditions."""
        steps = [
            {
                "name": "check_availability",
                "method": "http",
                "type": "crawl",
                "config": {"url": "https://example.com/check"},
                "selectors": {
                    "item_count": ".items-count",
                },
            },
            {
                "name": "fetch_items",
                "method": "http",
                "type": "scrape",
                "config": {"url": "https://example.com/items"},
                "run_only_if": "{{check_availability.item_count}} > 0",
                "selectors": {
                    "items": {
                        "selector": ".item",
                        "type": "array",
                    }
                },
            },
        ]

        orchestrator = StepOrchestrator(
            job_id="test-job-3",
            website_id="test-site-3",
            base_url="https://example.com",
            steps=steps,
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            # First request returns 0 items
            check_response = AsyncMock()
            check_response.status_code = 200
            check_response.text = '<html><div class="items-count">0</div></html>'
            check_response.headers = {"content-type": "text/html"}
            mock_request.return_value = check_response

            context = await orchestrator.execute_workflow()

            # Step 1 should complete
            assert "check_availability" in context.step_results
            assert context.step_results["check_availability"].success

            # Step 2 should be skipped
            assert "fetch_items" in context.step_results
            fetch_items_result = context.step_results["fetch_items"]
            assert "skipped" in fetch_items_result.metadata
            assert fetch_items_result.metadata["skipped"] is True

    @pytest.mark.asyncio
    async def test_skip_if_condition(self):
        """Test skip_if condition (opposite of run_only_if)."""
        steps = [
            {
                "name": "check_status",
                "method": "http",
                "type": "crawl",
                "config": {"url": "https://example.com/status"},
                "selectors": {
                    "status": ".status",
                },
            },
            {
                "name": "process_data",
                "method": "http",
                "type": "scrape",
                "config": {"url": "https://example.com/data"},
                "skip_if": "{{check_status.status}} == 'unavailable'",
                "selectors": {
                    "data": ".data",
                },
            },
        ]

        orchestrator = StepOrchestrator(
            job_id="test-job-4",
            website_id="test-site-4",
            base_url="https://example.com",
            steps=steps,
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            # Status check returns unavailable
            status_response = AsyncMock()
            status_response.status_code = 200
            status_response.text = '<html><div class="status">unavailable</div></html>'
            status_response.headers = {"content-type": "text/html"}
            mock_request.return_value = status_response

            context = await orchestrator.execute_workflow()

            # Step 1 should complete
            assert context.step_results["check_status"].success

            # Step 2 should be skipped
            process_result = context.step_results["process_data"]
            assert process_result.metadata.get("skipped") is True

    @pytest.mark.asyncio
    async def test_partial_failure_in_multi_url_step(self):
        """Test handling when some URLs succeed and others fail."""
        steps = [
            {
                "name": "fetch_list",
                "method": "http",
                "type": "crawl",
                "config": {"url": "https://example.com/list"},
                "selectors": {
                    "urls": {
                        "selector": "a",
                        "attribute": "href",
                        "type": "array",
                    }
                },
            },
            {
                "name": "fetch_pages",
                "method": "http",
                "type": "scrape",
                "input_from": "fetch_list.urls",
                "selectors": {
                    "content": ".content",
                },
            },
        ]

        orchestrator = StepOrchestrator(
            job_id="test-job-5",
            website_id="test-site-5",
            base_url="https://example.com",
            steps=steps,
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            # List page
            list_response = AsyncMock()
            list_response.status_code = 200
            list_response.text = """
                <html>
                    <a href="/page1">Page 1</a>
                    <a href="/page2">Page 2</a>
                </html>
            """
            list_response.headers = {"content-type": "text/html"}

            # First page succeeds
            success_response = AsyncMock()
            success_response.status_code = 200
            success_response.text = '<html><div class="content">Content 1</div></html>'
            success_response.headers = {"content-type": "text/html"}

            # Second page fails
            fail_response = AsyncMock()
            fail_response.status_code = 404
            fail_response.text = "Not Found"
            fail_response.headers = {"content-type": "text/html"}

            mock_request.side_effect = [list_response, success_response, fail_response]

            context = await orchestrator.execute_workflow()

            # Step 2 should show partial success
            step2 = context.step_results["fetch_pages"]
            assert step2.metadata["total_urls"] == 2
            assert step2.metadata["successful_urls"] == 1
            assert step2.metadata["failed_urls"] == 1
            # Step is considered successful if at least one URL succeeded
            assert step2.success

    @pytest.mark.asyncio
    async def test_dependency_cycle_detection(self):
        """Test that circular dependencies are detected."""
        steps = [
            {"name": "step1", "method": "http", "type": "crawl", "input_from": "step2.data"},
            {"name": "step2", "method": "http", "type": "crawl", "input_from": "step1.data"},
        ]

        orchestrator = StepOrchestrator(
            job_id="test-job-6",
            website_id="test-site-6",
            base_url="https://example.com",
            steps=steps,
        )

        # Should raise ValueError about circular dependency
        with pytest.raises(ValueError, match="Circular dependency detected"):
            await orchestrator.execute_workflow()

    @pytest.mark.asyncio
    async def test_missing_dependency_step(self):
        """Test error when step depends on non-existent step."""
        steps = [
            {
                "name": "step1",
                "method": "http",
                "type": "crawl",
                "input_from": "nonexistent.data",
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-job-7",
            website_id="test-site-7",
            base_url="https://example.com",
            steps=steps,
        )

        # Should raise ValueError about missing dependency
        with pytest.raises(ValueError, match="depends on non-existent step"):
            await orchestrator.execute_workflow()

    @pytest.mark.asyncio
    async def test_workflow_cancellation_between_steps(self):
        """Test that workflow can be cancelled between steps."""
        steps = [
            {
                "name": "step1",
                "method": "http",
                "type": "crawl",
                "config": {"url": "https://example.com/step1"},
                "selectors": {"data": ".data"},
            },
            {
                "name": "step2",
                "method": "http",
                "type": "crawl",
                "config": {"url": "https://example.com/step2"},
                "selectors": {"data": ".data"},
            },
            {
                "name": "step3",
                "method": "http",
                "type": "crawl",
                "config": {"url": "https://example.com/step3"},
                "selectors": {"data": ".data"},
            },
        ]

        # Mock cancellation flag
        mock_cancellation_flag = MagicMock()
        # Return False first (step1 runs), then True (cancel before step2)
        mock_cancellation_flag.is_cancelled = AsyncMock(side_effect=[False, True])

        orchestrator = StepOrchestrator(
            job_id="test-job-cancel",
            website_id="test-site-cancel",
            base_url="https://example.com",
            steps=steps,
            cancellation_flag=mock_cancellation_flag,
        )

        with patch("httpx.AsyncClient.request") as mock_request:
            mock_response = AsyncMock()
            mock_response.status_code = 200
            mock_response.text = '<html><div class="data">Test</div></html>'
            mock_response.headers = {"content-type": "text/html"}
            mock_request.return_value = mock_response

            context = await orchestrator.execute_workflow()

            # Verify workflow was cancelled
            assert context.metadata.get("cancelled") is True

            # Only first step in execution order should have executed
            # (dependency validator determines order, not definition order)
            assert len(context.step_results) == 1
            first_step = list(context.step_results.keys())[0]
            assert context.step_results[first_step].success

            # Other steps should not have executed
            assert len(context.step_results) < len(steps)

            # Cancellation flag should have been checked twice:
            # once before first step (returns False), once before second step (returns True)
            assert mock_cancellation_flag.is_cancelled.call_count == 2
