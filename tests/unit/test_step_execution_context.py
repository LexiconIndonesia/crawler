"""Unit tests for step execution context."""

from crawler.services.step_execution_context import StepExecutionContext, StepResult


class TestStepResult:
    """Test suite for StepResult."""

    def test_success_property_with_no_error(self):
        """Test success property returns True when no error."""
        result = StepResult(
            step_name="test_step",
            status_code=200,
            error=None,
        )

        assert result.success is True

    def test_success_property_with_error(self):
        """Test success property returns False when error exists."""
        result = StepResult(
            step_name="test_step",
            error="Something went wrong",
        )

        assert result.success is False

    def test_success_property_with_bad_status_code(self):
        """Test success property returns False with error status code."""
        result = StepResult(
            step_name="test_step",
            status_code=500,
            error=None,
        )

        assert result.success is False

    def test_success_property_with_successful_status_code(self):
        """Test success property returns True with 2xx status code."""
        result = StepResult(
            step_name="test_step",
            status_code=201,
            error=None,
        )

        assert result.success is True


class TestStepExecutionContext:
    """Test suite for StepExecutionContext."""

    def test_initialization(self):
        """Test context initialization."""
        context = StepExecutionContext(
            job_id="job123",
            website_id="site456",
        )

        assert context.job_id == "job123"
        assert context.website_id == "site456"
        assert context.variables == {}
        assert context.step_results == {}
        assert context.execution_order == []

    def test_add_result(self):
        """Test adding step result to context."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        result = StepResult(
            step_name="step1",
            status_code=200,
            extracted_data={"key": "value"},
        )

        context.add_result(result)

        assert "step1" in context.step_results
        assert context.step_results["step1"] == result
        assert context.execution_order == ["step1"]

    def test_get_result(self):
        """Test retrieving step result from context."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        result = StepResult(step_name="step1", extracted_data={"key": "value"})
        context.add_result(result)

        retrieved = context.get_result("step1")

        assert retrieved == result
        assert retrieved.extracted_data == {"key": "value"}

    def test_get_result_nonexistent(self):
        """Test retrieving nonexistent step result returns None."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        result = context.get_result("nonexistent")

        assert result is None

    def test_get_step_output(self):
        """Test getting extracted data from step."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        result = StepResult(
            step_name="step1",
            extracted_data={"urls": ["url1", "url2"]},
        )
        context.add_result(result)

        output = context.get_step_output("step1")

        assert output == {"urls": ["url1", "url2"]}

    def test_get_step_output_failed_step(self):
        """Test getting output from failed step returns empty dict."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        result = StepResult(
            step_name="step1",
            error="Failed",
            extracted_data={"key": "value"},
        )
        context.add_result(result)

        output = context.get_step_output("step1")

        assert output == {}

    def test_get_step_output_nonexistent(self):
        """Test getting output from nonexistent step returns empty dict."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        output = context.get_step_output("nonexistent")

        assert output == {}

    def test_set_and_get_variable(self):
        """Test setting and getting context variables."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        context.set_variable("api_key", "secret123")
        context.set_variable("base_url", "https://example.com")

        assert context.get_variable("api_key") == "secret123"
        assert context.get_variable("base_url") == "https://example.com"

    def test_get_variable_with_default(self):
        """Test getting variable with default value."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        result = context.get_variable("nonexistent", default="default_value")

        assert result == "default_value"

    def test_has_step_result(self):
        """Test checking if step result exists."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        result = StepResult(step_name="step1")
        context.add_result(result)

        assert context.has_step_result("step1") is True
        assert context.has_step_result("step2") is False

    def test_get_failed_steps(self):
        """Test getting list of failed steps."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        context.add_result(StepResult(step_name="step1", status_code=200))
        context.add_result(StepResult(step_name="step2", error="Failed"))
        context.add_result(StepResult(step_name="step3", status_code=500))
        context.add_result(StepResult(step_name="step4", status_code=201))

        failed = context.get_failed_steps()

        assert set(failed) == {"step2", "step3"}

    def test_get_successful_steps(self):
        """Test getting list of successful steps."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        context.add_result(StepResult(step_name="step1", status_code=200))
        context.add_result(StepResult(step_name="step2", error="Failed"))
        context.add_result(StepResult(step_name="step3", status_code=500))
        context.add_result(StepResult(step_name="step4", status_code=201))

        successful = context.get_successful_steps()

        assert set(successful) == {"step1", "step4"}

    def test_execution_order_tracking(self):
        """Test that execution order is tracked correctly."""
        context = StepExecutionContext(job_id="job1", website_id="site1")

        context.add_result(StepResult(step_name="step3"))
        context.add_result(StepResult(step_name="step1"))
        context.add_result(StepResult(step_name="step2"))

        assert context.execution_order == ["step3", "step1", "step2"]

    def test_to_dict_serialization(self):
        """Test converting context to dictionary."""
        context = StepExecutionContext(job_id="job1", website_id="site1")
        context.set_variable("key", "value")

        context.add_result(
            StepResult(
                step_name="step1",
                status_code=200,
                extracted_data={"data": "test"},
            )
        )
        context.add_result(StepResult(step_name="step2", error="Failed"))

        result_dict = context.to_dict()

        assert result_dict["job_id"] == "job1"
        assert result_dict["website_id"] == "site1"
        assert result_dict["variables"] == {"key": "value"}
        assert "step1" in result_dict["step_results"]
        assert "step2" in result_dict["step_results"]
        assert result_dict["execution_order"] == ["step1", "step2"]
        assert "step2" in result_dict["failed_steps"]
        assert "step1" in result_dict["successful_steps"]
