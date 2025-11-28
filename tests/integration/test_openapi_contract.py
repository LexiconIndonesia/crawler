"""
Contract tests to ensure FastAPI implementation matches openapi.yaml specification.

These tests validate that the running application's OpenAPI spec matches
the contract defined in openapi.yaml, preventing drift between the two.
"""

from pathlib import Path

import pytest
import yaml

from main import create_app


def load_contract_spec() -> dict:
    """Load the OpenAPI contract from openapi.yaml."""
    contract_path = Path(__file__).parent.parent.parent / "openapi.yaml"
    with contract_path.open() as f:
        return yaml.safe_load(f)


class TestOpenAPIContract:
    """Test suite for OpenAPI contract validation."""

    @pytest.fixture
    def app(self):
        """Create FastAPI app instance."""
        return create_app()

    @pytest.fixture
    def contract_spec(self) -> dict:
        """Load contract specification."""
        return load_contract_spec()

    @pytest.fixture
    def fastapi_spec(self, app) -> dict:
        """Get FastAPI-generated OpenAPI specification."""
        return app.openapi()

    def test_api_version_matches(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify API version matches between contract and implementation."""
        contract_version = contract_spec["info"]["version"]
        fastapi_version = fastapi_spec["info"]["version"]

        assert fastapi_version == contract_version, (
            f"API version mismatch: FastAPI={fastapi_version}, Contract={contract_version}"
        )

    def test_api_title_matches(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify API title matches between contract and implementation."""
        contract_title = contract_spec["info"]["title"]
        fastapi_title = fastapi_spec["info"]["title"]

        assert fastapi_title == contract_title, (
            f"API title mismatch: FastAPI={fastapi_title}, Contract={contract_title}"
        )

    def test_all_contract_paths_implemented(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify all paths in contract are implemented in FastAPI."""
        contract_paths = set(contract_spec.get("paths", {}).keys())
        fastapi_paths = set(fastapi_spec.get("paths", {}).keys())

        missing_paths = contract_paths - fastapi_paths
        assert not missing_paths, (
            f"Paths defined in contract but missing in FastAPI: {missing_paths}"
        )

    def test_no_undocumented_paths(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify FastAPI doesn't expose paths not in contract."""
        contract_paths = set(contract_spec.get("paths", {}).keys())
        fastapi_paths = set(fastapi_spec.get("paths", {}).keys())

        extra_paths = fastapi_paths - contract_paths
        assert not extra_paths, f"Paths implemented in FastAPI but not in contract: {extra_paths}"

    def test_http_methods_match(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify HTTP methods for each path match between contract and implementation."""
        mismatches = []

        for path, contract_methods in contract_spec.get("paths", {}).items():
            fastapi_methods = fastapi_spec.get("paths", {}).get(path, {})

            contract_method_set = {m for m in contract_methods if m not in ["parameters"]}
            fastapi_method_set = {m for m in fastapi_methods if m not in ["parameters"]}

            if contract_method_set != fastapi_method_set:
                mismatches.append(
                    {
                        "path": path,
                        "contract_methods": contract_method_set,
                        "fastapi_methods": fastapi_method_set,
                    }
                )

        assert not mismatches, "HTTP method mismatches found:\n" + "\n".join(
            f"  {m['path']}: Contract={m['contract_methods']}, FastAPI={m['fastapi_methods']}"
            for m in mismatches
        )

    def test_operation_ids_match(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify operation IDs match for each endpoint (where defined)."""
        mismatches = []

        for path, contract_methods in contract_spec.get("paths", {}).items():
            fastapi_methods = fastapi_spec.get("paths", {}).get(path, {})

            for method in contract_methods:
                if method == "parameters":
                    continue

                contract_op_id = contract_methods[method].get("operationId")
                fastapi_op_id = fastapi_methods.get(method, {}).get("operationId")

                if contract_op_id and contract_op_id != fastapi_op_id:
                    mismatches.append(
                        {
                            "path": path,
                            "method": method,
                            "contract": contract_op_id,
                            "fastapi": fastapi_op_id,
                        }
                    )

        assert not mismatches, "Operation ID mismatches found:\n" + "\n".join(
            f"  {m['path']} ({m['method']}): Contract={m['contract']}, FastAPI={m['fastapi']}"
            for m in mismatches
        )

    def test_response_schemas_defined(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify all endpoints have response schemas defined in FastAPI."""
        missing_responses = []

        for path, contract_methods in contract_spec.get("paths", {}).items():
            fastapi_methods = fastapi_spec.get("paths", {}).get(path, {})

            for method in contract_methods:
                if method == "parameters":
                    continue

                # Check if the endpoint has at least one successful response (2xx)
                contract_responses = contract_methods[method].get("responses", {})
                fastapi_responses = fastapi_methods.get(method, {}).get("responses", {})

                has_success_response = any(status.startswith("2") for status in fastapi_responses)

                if not has_success_response and contract_responses:
                    missing_responses.append({"path": path, "method": method.upper()})

        assert not missing_responses, (
            "Endpoints missing response schemas in FastAPI:\n"
            + "\n".join(f"  {r['method']} {r['path']}" for r in missing_responses)
        )

    def test_tags_consistency(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify tags used in paths are defined in the contract."""
        # Get all tags from contract definition
        contract_tag_names = {tag["name"] for tag in contract_spec.get("tags", [])}

        # Get all tags used in paths
        used_tags = set()
        for path_methods in contract_spec.get("paths", {}).values():
            for method_data in path_methods.values():
                if isinstance(method_data, dict) and "tags" in method_data:
                    used_tags.update(method_data["tags"])

        undefined_tags = used_tags - contract_tag_names
        assert not undefined_tags, (
            f"Tags used in paths but not defined in contract: {undefined_tags}"
        )

    def test_required_components_present(self, contract_spec: dict, fastapi_spec: dict) -> None:
        """Verify key components schemas from contract exist in FastAPI spec."""
        fastapi_schemas = set(fastapi_spec.get("components", {}).get("schemas", {}).keys())

        # Check for critical request/response models
        critical_schemas = {
            "CreateWebsiteRequest",
            "WebsiteResponse",
            "HealthResponse",
            "ErrorResponse",
        }

        missing_critical = critical_schemas - fastapi_schemas
        assert not missing_critical, f"Critical schemas missing in FastAPI: {missing_critical}"

    def test_openapi_version_compatibility(self, fastapi_spec: dict) -> None:
        """Verify OpenAPI version is compatible (3.x)."""
        openapi_version = fastapi_spec.get("openapi", "")
        assert openapi_version.startswith("3."), f"Expected OpenAPI 3.x, got: {openapi_version}"

    def test_contract_is_valid_yaml(self) -> None:
        """Verify openapi.yaml is valid YAML and loads correctly."""
        try:
            spec = load_contract_spec()
            assert isinstance(spec, dict)
            assert "openapi" in spec
            assert "info" in spec
            assert "paths" in spec
        except Exception as e:
            pytest.fail(f"Contract YAML is invalid: {e}")


class TestContractCompleteness:
    """Tests to ensure contract documentation is complete."""

    @pytest.fixture
    def contract_spec(self) -> dict:
        """Load contract specification."""
        return load_contract_spec()

    def test_all_paths_have_summaries(self, contract_spec: dict) -> None:
        """Verify all endpoints have summary documentation."""
        missing_summaries = []

        for path, methods in contract_spec.get("paths", {}).items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                if not details.get("summary"):
                    missing_summaries.append(f"{method.upper()} {path}")

        assert not missing_summaries, "Endpoints missing summaries in contract:\n" + "\n".join(
            f"  {e}" for e in missing_summaries
        )

    def test_all_paths_have_descriptions(self, contract_spec: dict) -> None:
        """Verify all endpoints have description documentation."""
        missing_descriptions = []

        for path, methods in contract_spec.get("paths", {}).items():
            for method, details in methods.items():
                if method == "parameters":
                    continue
                if not details.get("description"):
                    missing_descriptions.append(f"{method.upper()} {path}")

        assert not missing_descriptions, (
            "Endpoints missing descriptions in contract:\n"
            + "\n".join(f"  {e}" for e in missing_descriptions)
        )

    def test_all_post_endpoints_have_examples(self, contract_spec: dict) -> None:
        """Verify POST endpoints have request body examples."""
        missing_examples = []

        for path, methods in contract_spec.get("paths", {}).items():
            if "post" in methods:
                request_body = methods["post"].get("requestBody", {})
                content = request_body.get("content", {})
                json_content = content.get("application/json", {})

                if not json_content.get("examples") and not json_content.get("example"):
                    missing_examples.append(f"POST {path}")

        assert not missing_examples, (
            "POST endpoints missing request examples in contract:\n"
            + "\n".join(f"  {e}" for e in missing_examples)
        )
