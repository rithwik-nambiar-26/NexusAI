"""Integration tests for the planner API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create a test client backed by an in-memory database."""
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    return TestClient(app)


def test_plan_endpoint_with_explicit_intent(client: TestClient):
    """Test POST /api/v1/planner/plan with an explicit intent."""
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Read data/sample/product_manual.md and summarise the warranty conditions.",
            "intent": "document_summarisation",
            "source": "explicit",
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert "plan" in data
    assert "request_id" in data

    plan = data["plan"]
    assert plan["plan_status"] == "ready"
    assert plan["intent"] == "document_summarisation"
    assert len(plan["tasks"]) >= 2
    assert len(plan["execution_order"]) == len(plan["tasks"])
    assert plan["source"] == "explicit"


def test_plan_endpoint_rejects_empty_text(client: TestClient):
    """Test that an empty request is rejected by validation."""
    response = client.post("/api/v1/planner/plan", json={"text": ""})
    assert response.status_code == 422


def test_plan_endpoint_rejects_missing_text(client: TestClient):
    """Test that a missing text field is rejected by validation."""
    response = client.post("/api/v1/planner/plan", json={})
    assert response.status_code == 422


def test_plan_endpoint_rejects_unknown_intent(client: TestClient):
    """Test that an unknown intent yields an invalid plan, not a crash."""
    response = client.post(
        "/api/v1/planner/plan",
        json={"text": "Do something", "intent": "not_a_real_intent"},
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["plan_status"] == "invalid"
    assert plan["tasks"] == []


def test_plan_endpoint_destructive_intent_requires_approval(client: TestClient):
    """Test that a destructive intent is flagged and produces no tasks."""
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Delete every file in the notes/ directory.",
            "intent": "destructive_operation",
            "source": "explicit",
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["plan_status"] == "invalid"
    assert plan["requires_approval"] is True
    assert plan["tasks"] == []
    assert plan["clarification_required"] is True


def test_plan_endpoint_includes_dependency_graph(client: TestClient):
    """Test that the response exposes the dependency graph."""
    response = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Analyse data/sample/sales_2026.csv and identify the top region.",
            "intent": "data_analysis",
            "source": "explicit",
        },
    )

    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["dependencies"]
    for prerequisite, dependent in plan["dependencies"]:
        assert prerequisite != dependent
    assert plan["parallel_levels"]


def test_plan_endpoint_uses_classifier_when_intent_absent(client: TestClient):
    """Test that the endpoint classifies the request when no intent is given."""
    response = client.post(
        "/api/v1/planner/plan",
        json={"text": "Summarise data/sample/product_manual.md"},
    )

    # Either the classifier produced a usable intent, or the plan records
    # that clarification is required. Both are valid outcomes; the request
    # must never fail with a server error.
    assert response.status_code == 200
    plan = response.json()["plan"]
    assert plan["source"] == "classifier"
    if plan["plan_status"] == "ready":
        assert plan["intent"] is not None
    else:
        assert plan["clarification_required"] is True


def test_planner_status_endpoint(client: TestClient):
    """Test GET /api/v1/planner/status."""
    response = client.get("/api/v1/planner/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "request_id" in data


def test_get_plan_reports_no_persistence(client: TestClient):
    """Test that plan retrieval reports that persistence is not implemented."""
    response = client.get("/api/v1/planner/plan_abc123")
    assert response.status_code == 200
    data = response.json()
    assert data["plan_id"] == "plan_abc123"
    assert data["available"] is False


def test_update_task_status_reports_no_persistence(client: TestClient):
    """Test that task status updates report that persistence is not implemented."""
    response = client.post(
        "/api/v1/planner/plan_abc123/task-status",
        json={"task_id": "t1", "status": "completed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["task_id"] == "t1"
    assert data["available"] is False


def test_openapi_schema_includes_planner(client: TestClient):
    """Test that the planner routes appear in the OpenAPI schema."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/api/v1/planner/plan" in schema["paths"]
    assert "/api/v1/planner/status" in schema["paths"]


def test_existing_endpoints_still_work(client: TestClient):
    """Test that the Day 1 and Day 2 endpoints are unaffected."""
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/system/status").status_code == 200
    assert client.get("/api/v1/intent/intents").status_code == 200
    assert client.get("/api/v1/workflows").status_code == 200
