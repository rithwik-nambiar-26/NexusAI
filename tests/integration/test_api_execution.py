"""Integration tests for the execution API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app
from nexusai.ml.planner.service import create_plan


@pytest.fixture
def client(tmp_path) -> TestClient:
    """Create a test client with isolated database and vector index."""
    settings = Settings(
        database_url="sqlite:///:memory:",
        vector_store_dir=str(tmp_path / "vectors"),
    )
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def ingested(client) -> TestClient:
    """Return a client with a document already ingested."""
    client.post(
        "/api/v1/documents/ingest",
        json={"path": "data/sample/product_manual.md"},
    )
    return client


def _plan_payload(request: str, intent: str = "document_summarisation") -> dict:
    plan, _ = create_plan(request=request, intent=intent, source="explicit")
    return plan.model_dump(mode="json")


def test_execution_status_endpoint(client: TestClient):
    """Test GET /api/v1/execution/status."""
    response = client.get("/api/v1/execution/status")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert "document.read" in data["registered_capabilities"]


def test_tools_endpoint(client: TestClient):
    """Test GET /api/v1/execution/tools."""
    response = client.get("/api/v1/execution/tools")
    assert response.status_code == 200
    data = response.json()
    assert data["count"] == 3
    capabilities = {tool["capability"] for tool in data["tools"]}
    assert capabilities == {"document.read", "document.extract", "llm.summarise"}

    for tool in data["tools"]:
        assert tool["requires_approval"] is False
        assert tool["risk"] == "safe"
        assert tool["input_fields"]


def test_execute_plan_endpoint(ingested: TestClient):
    """Test POST /api/v1/execution/execute."""
    response = ingested.post(
        "/api/v1/execution/execute",
        json={
            "plan": _plan_payload(
                "Read data/sample/product_manual.md and summarise the warranty conditions."
            )
        },
    )

    assert response.status_code == 200
    report = response.json()["report"]
    assert report["status"] in ("completed", "partially_completed")

    completed = [
        result
        for result in report["task_results"]
        if result["status"] == "completed"
    ]
    assert len(completed) == 3
    assert {r["capability"] for r in completed} == {
        "document.read",
        "document.extract",
        "llm.summarise",
    }


def test_execute_rejects_an_invalid_plan(client: TestClient):
    """Test that a malformed plan is refused with a clear error."""
    response = client.post(
        "/api/v1/execution/execute",
        json={"plan": {"not": "a plan"}},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_plan"


def test_execute_rejects_a_plan_with_a_cyclic_dependency(client: TestClient):
    """Test that a cyclic plan is refused by the engine."""
    plan = _plan_payload("Read data/sample/product_manual.md and summarise it.")
    plan["dependencies"] = [["t1", "t2"], ["t2", "t1"]]

    response = client.post("/api/v1/execution/execute", json={"plan": plan})
    assert response.status_code == 200
    report = response.json()["report"]
    assert report["status"] == "invalid"
    assert report["task_results"] == []


def test_execute_skips_unregistered_capabilities(ingested: TestClient):
    """Test that a task with no registered capability is skipped."""
    plan = _plan_payload("Read data/sample/product_manual.md and summarise it.")
    plan["tasks"][0]["required_capabilities"] = ["not.registered"]

    response = ingested.post("/api/v1/execution/execute", json={"plan": plan})
    report = response.json()["report"]
    skipped = [
        r for r in report["task_results"] if r["status"] == "skipped"
    ]
    assert skipped


def test_execute_records_a_duplicate_skip(ingested: TestClient):
    """Test that running the same plan twice does not repeat the work."""
    payload = {
        "plan": _plan_payload(
            "Read data/sample/product_manual.md and summarise the warranty conditions."
        )
    }
    first = ingested.post("/api/v1/execution/execute", json=payload).json()["report"]
    second = ingested.post("/api/v1/execution/execute", json=payload).json()["report"]

    assert first["status"] in ("completed", "partially_completed")
    # The second run skips every task: the chain had already run.
    assert all(
        result["status"] == "skipped" for result in second["task_results"]
    )
    assert second["status"] == "completed"
    assert "already been executed" in second["task_results"][0]["error"]


def test_approval_endpoint_requires_a_report(client: TestClient):
    """Test that approving without an execution is refused."""
    response = client.post(
        "/api/v1/execution/approve",
        json={"task_id": "t1", "granted": True},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "no_execution_report"


def test_openapi_schema_includes_execution_routes(client: TestClient):
    """Test that the execution routes appear in the OpenAPI schema."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/execution/execute" in paths
    assert "/api/v1/execution/tools" in paths
    assert "/api/v1/execution/status" in paths


def test_existing_endpoints_still_work(ingested: TestClient):
    """Test that the earlier endpoints are unaffected."""
    assert ingested.get("/health").status_code == 200
    assert ingested.get("/api/v1/system/status").status_code == 200
    assert ingested.get("/api/v1/intent/intents").status_code == 200
    assert ingested.get("/api/v1/planner/status").status_code == 200
    assert ingested.get("/api/v1/documents/capabilities").status_code == 200
    assert ingested.get("/api/v1/workflows").status_code == 200


def test_document_api_path_traversal_is_refused(client: TestClient):
    """Test that the document API refuses a path outside the allowed roots."""
    response = client.post(
        "/api/v1/documents/ingest",
        json={"path": "../../../etc/passwd"},
    )
    assert response.status_code == 200
    result = response.json()["result"]
    assert result["status"] == "path_not_allowed"
    assert result["document"] is None
