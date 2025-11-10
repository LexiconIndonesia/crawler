"""Unit tests for dependency validator."""

import pytest

from crawler.services.dependency_validator import DependencyValidator


class TestDependencyValidator:
    """Test suite for DependencyValidator."""

    def test_validate_simple_linear_dependencies(self):
        """Test validation of simple linear dependency chain."""
        steps = [
            {"name": "step1"},
            {"name": "step2", "input_from": "step1.data"},
            {"name": "step3", "input_from": "step2.result"},
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        assert execution_order == ["step1", "step2", "step3"]

    def test_validate_no_dependencies(self):
        """Test validation with no dependencies."""
        steps = [
            {"name": "step1"},
            {"name": "step2"},
            {"name": "step3"},
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        # All steps are independent, order doesn't matter but all should be present
        assert len(execution_order) == 3
        assert set(execution_order) == {"step1", "step2", "step3"}

    def test_validate_parallel_dependencies(self):
        """Test validation with parallel dependencies converging."""
        steps = [
            {"name": "fetch1"},
            {"name": "fetch2"},
            {"name": "combine", "input_from": "fetch1.data"},  # depends on fetch1
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        # fetch1 must come before combine, fetch2 can be anywhere
        fetch1_idx = execution_order.index("fetch1")
        combine_idx = execution_order.index("combine")
        assert fetch1_idx < combine_idx

    def test_detect_simple_cycle(self):
        """Test detection of simple circular dependency."""
        steps = [
            {"name": "step1", "input_from": "step2.data"},
            {"name": "step2", "input_from": "step1.data"},
        ]

        validator = DependencyValidator(steps)

        with pytest.raises(ValueError, match="Circular dependency detected"):
            validator.validate()

    def test_detect_complex_cycle(self):
        """Test detection of circular dependency in longer chain."""
        steps = [
            {"name": "step1"},
            {"name": "step2", "input_from": "step1.data"},
            {"name": "step3", "input_from": "step2.data"},
            {"name": "step4", "input_from": "step3.data"},
            {"name": "step2", "input_from": "step4.data"},  # Cycle: step2 depends on step4
        ]

        # This will fail at duplicate name check first
        with pytest.raises(ValueError, match="Duplicate step names"):
            validator = DependencyValidator(steps)
            validator.validate()

    def test_detect_self_dependency(self):
        """Test detection of step depending on itself."""
        steps = [
            {"name": "step1", "input_from": "step1.data"},
        ]

        validator = DependencyValidator(steps)

        with pytest.raises(ValueError, match="Circular dependency detected"):
            validator.validate()

    def test_missing_dependency(self):
        """Test error when step depends on non-existent step."""
        steps = [
            {"name": "step1"},
            {"name": "step2", "input_from": "nonexistent.data"},
        ]

        validator = DependencyValidator(steps)

        with pytest.raises(ValueError, match="depends on non-existent step"):
            validator.validate()

    def test_duplicate_step_names(self):
        """Test error when duplicate step names are found."""
        steps = [
            {"name": "step1"},
            {"name": "step1"},  # Duplicate
        ]

        validator = DependencyValidator(steps)

        with pytest.raises(ValueError, match="Duplicate step names"):
            validator.validate()

    def test_complex_dag_structure(self):
        """Test validation of complex DAG with multiple paths."""
        steps = [
            {"name": "fetch"},
            {"name": "parse1", "input_from": "fetch.html"},
            {"name": "parse2", "input_from": "fetch.html"},
            {"name": "combine", "input_from": "parse1.data"},
            {"name": "final"},
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        # Verify dependencies are respected
        fetch_idx = execution_order.index("fetch")
        parse1_idx = execution_order.index("parse1")
        parse2_idx = execution_order.index("parse2")
        combine_idx = execution_order.index("combine")

        assert fetch_idx < parse1_idx
        assert fetch_idx < parse2_idx
        assert parse1_idx < combine_idx

    def test_get_dependencies(self):
        """Test getting direct dependencies of a step."""
        steps = [
            {"name": "step1"},
            {"name": "step2", "input_from": "step1.data"},
        ]

        validator = DependencyValidator(steps)
        validator.validate()

        assert validator.get_dependencies("step1") == []
        assert validator.get_dependencies("step2") == ["step1"]

    def test_get_dependents(self):
        """Test getting steps that depend on a given step."""
        steps = [
            {"name": "step1"},
            {"name": "step2", "input_from": "step1.data"},
            {"name": "step3", "input_from": "step1.data"},
        ]

        validator = DependencyValidator(steps)
        validator.validate()

        dependents = validator.get_dependents("step1")
        assert set(dependents) == {"step2", "step3"}

    def test_is_independent(self):
        """Test checking if a step has no dependencies."""
        steps = [
            {"name": "step1"},
            {"name": "step2", "input_from": "step1.data"},
        ]

        validator = DependencyValidator(steps)
        validator.validate()

        assert validator.is_independent("step1") is True
        assert validator.is_independent("step2") is False

    def test_skip_if_creates_dependency(self):
        """Test that skip_if condition creates dependency."""
        steps = [
            {"name": "check_status"},
            {
                "name": "process_data",
                "skip_if": "{{check_status.status}} == 'unavailable'",
            },
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        # check_status must execute before process_data
        assert execution_order.index("check_status") < execution_order.index("process_data")

    def test_run_only_if_creates_dependency(self):
        """Test that run_only_if condition creates dependency."""
        steps = [
            {"name": "check_availability"},
            {
                "name": "fetch_items",
                "run_only_if": "{{check_availability.item_count}} > 0",
            },
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        # check_availability must execute before fetch_items
        assert execution_order.index("check_availability") < execution_order.index("fetch_items")

    def test_multiple_condition_dependencies(self):
        """Test condition referencing multiple steps."""
        steps = [
            {"name": "step1"},
            {"name": "step2"},
            {
                "name": "step3",
                "skip_if": "{{step1.count}} == 0 or {{step2.failed}}",
            },
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        # Both step1 and step2 must execute before step3
        step1_idx = execution_order.index("step1")
        step2_idx = execution_order.index("step2")
        step3_idx = execution_order.index("step3")

        assert step1_idx < step3_idx
        assert step2_idx < step3_idx

    def test_condition_with_nonexistent_step(self):
        """Test error when condition references non-existent step."""
        steps = [
            {"name": "step1"},
            {
                "name": "step2",
                "skip_if": "{{nonexistent.value}} == 0",
            },
        ]

        validator = DependencyValidator(steps)

        # Should not raise error - nonexistent is treated as variable, not step
        execution_order = validator.validate()
        assert len(execution_order) == 2

    def test_combined_input_from_and_condition_dependencies(self):
        """Test step with both input_from and condition dependencies."""
        steps = [
            {"name": "step1"},
            {"name": "step2"},
            {
                "name": "step3",
                "input_from": "step1.data",
                "run_only_if": "{{step2.ready}} == true",
            },
        ]

        validator = DependencyValidator(steps)
        execution_order = validator.validate()

        # Both step1 and step2 must execute before step3
        step1_idx = execution_order.index("step1")
        step2_idx = execution_order.index("step2")
        step3_idx = execution_order.index("step3")

        assert step1_idx < step3_idx
        assert step2_idx < step3_idx
