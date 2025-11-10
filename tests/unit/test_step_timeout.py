"""Unit tests for step timeout enforcement."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from crawler.services.step_orchestrator import StepOrchestrator


class TestStepTimeout:
    """Test suite for step timeout enforcement."""

    @pytest.mark.asyncio
    async def test_step_timeout_enforcement(self):
        """Test that step execution is cancelled when timeout is exceeded."""
        # Define step with 1 second timeout
        steps = [
            {
                "name": "slow_step",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com/slow",
                    "timeout": 1,  # 1 second timeout
                },
                "selectors": {},
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-timeout-job",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock executor to simulate slow operation
        async def slow_execute(*args, **kwargs):
            """Simulate slow operation that exceeds timeout."""
            await asyncio.sleep(3)  # Sleep for 3 seconds (exceeds 1s timeout)
            return MagicMock()

        with patch.object(orchestrator.crawl_executor, "execute", side_effect=slow_execute):
            context = await orchestrator.execute_workflow()

            # Verify timeout was triggered
            assert "slow_step" in context.step_results
            step_result = context.step_results["slow_step"]
            assert not step_result.success
            assert "timeout" in step_result.error.lower()
            assert step_result.metadata.get("timeout") is True
            assert step_result.metadata.get("timeout_seconds") == 1

    @pytest.mark.asyncio
    async def test_step_completes_within_timeout(self):
        """Test that step completes successfully when within timeout limit."""
        # Define step with 5 second timeout
        steps = [
            {
                "name": "fast_step",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com/fast",
                    "timeout": 5,  # 5 second timeout
                },
                "selectors": {
                    "title": "h1",
                },
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-fast-job",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock executor to simulate fast operation
        async def fast_execute(*args, **kwargs):
            """Simulate fast operation that completes quickly."""
            await asyncio.sleep(0.1)  # Sleep for 100ms (well under 5s timeout)
            result = MagicMock()
            result.success = True
            result.status_code = 200
            result.content = "<html><h1>Title</h1></html>"
            result.extracted_data = {"title": "Title"}
            result.metadata = {}
            result.error = None
            return result

        with patch.object(orchestrator.crawl_executor, "execute", side_effect=fast_execute):
            context = await orchestrator.execute_workflow()

            # Verify step completed successfully
            assert "fast_step" in context.step_results
            step_result = context.step_results["fast_step"]
            assert step_result.success
            assert step_result.error is None
            assert step_result.metadata.get("timeout") is None
            assert step_result.metadata.get("execution_time_seconds") is not None
            assert step_result.metadata.get("execution_time_seconds") < 5
            assert step_result.metadata.get("timeout_configured") == 5

    @pytest.mark.asyncio
    async def test_timeout_metadata_tracking(self):
        """Test that timeout metadata is properly tracked in results."""
        steps = [
            {
                "name": "tracked_step",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com",
                    "timeout": 10,
                },
                "selectors": {},
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-metadata-job",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock executor
        async def mock_execute(*args, **kwargs):
            await asyncio.sleep(0.05)
            result = MagicMock()
            result.success = True
            result.status_code = 200
            result.content = ""
            result.extracted_data = {}
            result.metadata = {}
            result.error = None
            return result

        with patch.object(orchestrator.crawl_executor, "execute", side_effect=mock_execute):
            context = await orchestrator.execute_workflow()

            step_result = context.step_results["tracked_step"]
            assert step_result.success
            # Verify metadata contains timeout tracking
            assert "execution_time_seconds" in step_result.metadata
            assert "timeout_configured" in step_result.metadata
            assert step_result.metadata["timeout_configured"] == 10
            assert isinstance(step_result.metadata["execution_time_seconds"], (int, float))

    @pytest.mark.asyncio
    async def test_default_timeout_applied(self):
        """Test that default 30s timeout is applied when not specified."""
        steps = [
            {
                "name": "default_timeout_step",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com",
                    # No timeout specified - should use default 30s
                },
                "selectors": {},
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-default-timeout",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock executor
        async def mock_execute(*args, **kwargs):
            await asyncio.sleep(0.01)
            result = MagicMock()
            result.success = True
            result.status_code = 200
            result.content = ""
            result.extracted_data = {}
            result.metadata = {}
            result.error = None
            return result

        with patch.object(orchestrator.crawl_executor, "execute", side_effect=mock_execute):
            context = await orchestrator.execute_workflow()

            step_result = context.step_results["default_timeout_step"]
            assert step_result.success
            # Verify default timeout was applied
            assert step_result.metadata["timeout_configured"] == 30

    @pytest.mark.asyncio
    async def test_timeout_with_multiple_steps(self):
        """Test timeout enforcement works correctly across multiple steps."""
        steps = [
            {
                "name": "step1",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com/1",
                    "timeout": 5,
                },
                "selectors": {
                    "urls": {
                        "selector": "a",
                        "attribute": "href",
                        "type": "array",
                    }
                },
            },
            {
                "name": "step2_slow",
                "method": "http",
                "type": "scrape",
                "input_from": "step1.urls",
                "config": {
                    "timeout": 1,  # Very short timeout
                },
                "selectors": {
                    "content": "p",
                },
            },
        ]

        orchestrator = StepOrchestrator(
            job_id="test-multi-timeout",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock step1 to succeed quickly
        async def step1_execute(*args, **kwargs):
            await asyncio.sleep(0.1)
            result = MagicMock()
            result.success = True
            result.status_code = 200
            result.content = '<a href="/page1">Link</a><a href="/page2">Link2</a>'
            result.extracted_data = {"urls": ["/page1", "/page2"]}
            result.metadata = {}
            result.error = None
            return result

        # Mock step2 to timeout
        async def step2_execute(*args, **kwargs):
            await asyncio.sleep(3)  # Exceeds 1s timeout
            return MagicMock()

        with patch.object(orchestrator.crawl_executor, "execute", side_effect=step1_execute):
            with patch.object(orchestrator.scrape_executor, "execute", side_effect=step2_execute):
                context = await orchestrator.execute_workflow()

                # Verify step1 succeeded
                assert context.step_results["step1"].success
                assert context.step_results["step1"].metadata["timeout_configured"] == 5

                # Verify step2 timed out
                assert not context.step_results["step2_slow"].success
                assert "timeout" in context.step_results["step2_slow"].error.lower()
                assert context.step_results["step2_slow"].metadata.get("timeout") is True
                assert context.step_results["step2_slow"].metadata["timeout_seconds"] == 1

    @pytest.mark.asyncio
    async def test_timeout_error_logging(self):
        """Test that timeout events are properly logged."""
        steps = [
            {
                "name": "logging_step",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com",
                    "timeout": 1,
                },
                "selectors": {},
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-logging-job",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock slow executor
        async def slow_execute(*args, **kwargs):
            await asyncio.sleep(2)
            return MagicMock()

        # Patch logger to verify logging
        with patch("crawler.services.step_orchestrator.logger") as mock_logger:
            with patch.object(orchestrator.crawl_executor, "execute", side_effect=slow_execute):
                await orchestrator.execute_workflow()

                # Verify timeout was logged
                mock_logger.error.assert_any_call(
                    "step_timeout",
                    step_name="logging_step",
                    timeout_seconds=1,
                    execution_time_seconds=pytest.approx(1.0, abs=0.5),
                    job_id="test-logging-job",
                )

    @pytest.mark.asyncio
    async def test_global_timeout_override(self):
        """Test that step-level timeout overrides global timeout."""
        steps = [
            {
                "name": "override_step",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com",
                    "timeout": 15,  # Step-specific timeout
                },
                "selectors": {},
            }
        ]

        # Set global timeout to 30s
        global_config = {"timeout": 30}

        orchestrator = StepOrchestrator(
            job_id="test-override-job",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
            global_config=global_config,
        )

        # Mock executor
        async def mock_execute(*args, **kwargs):
            await asyncio.sleep(0.01)
            result = MagicMock()
            result.success = True
            result.status_code = 200
            result.content = ""
            result.extracted_data = {}
            result.metadata = {}
            result.error = None
            return result

        with patch.object(orchestrator.crawl_executor, "execute", side_effect=mock_execute):
            context = await orchestrator.execute_workflow()

            step_result = context.step_results["override_step"]
            assert step_result.success
            # Verify step-level timeout took precedence over global
            assert step_result.metadata["timeout_configured"] == 15

    @pytest.mark.asyncio
    async def test_execution_time_rounded(self):
        """Test that execution time is rounded to 3 decimal places."""
        steps = [
            {
                "name": "precision_step",
                "method": "http",
                "type": "crawl",
                "config": {
                    "url": "https://example.com",
                    "timeout": 10,
                },
                "selectors": {},
            }
        ]

        orchestrator = StepOrchestrator(
            job_id="test-precision-job",
            website_id="test-site",
            base_url="https://example.com",
            steps=steps,
        )

        # Mock executor with very short execution
        async def mock_execute(*args, **kwargs):
            await asyncio.sleep(0.123456789)  # Precise sleep
            result = MagicMock()
            result.success = True
            result.status_code = 200
            result.content = ""
            result.extracted_data = {}
            result.metadata = {}
            result.error = None
            return result

        with patch.object(orchestrator.crawl_executor, "execute", side_effect=mock_execute):
            context = await orchestrator.execute_workflow()

            step_result = context.step_results["precision_step"]
            execution_time = step_result.metadata["execution_time_seconds"]

            # Verify execution time is rounded to 3 decimal places
            assert isinstance(execution_time, float)
            # Check that the value has at most 3 decimal places
            # (by verifying it equals itself when rounded to 3 places)
            assert execution_time == round(execution_time, 3)
