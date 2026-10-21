"""Tests for the application error model and exception handlers."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.core.exceptions import (
    NexusAIError,
    NotFoundError,
    ServiceUnavailableError,
    ValidationError,
    register_exception_handlers,
)
from nexusai.app.main import create_app


def test_nexus_error_to_dict():
    err = NotFoundError("missing", code="x_not_found", status_code=404, details={"id": 1})
    payload = err.to_dict("req-1")
    assert payload["request_id"] == "req-1"
    assert payload["error"]["code"] == "x_not_found"
    assert payload["error"]["message"] == "missing"
    assert payload["error"]["details"] == {"id": 1}


def test_default_status_codes():
    assert NotFoundError("x").status_code == 404
    assert ServiceUnavailableError("x").status_code == 503
    assert ValidationError("x").status_code == 400
    assert NexusAIError("x").status_code == 500


def test_exception_handlers_return_consistent_shape():
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    register_exception_handlers(app)
    client = TestClient(app)

    # 404 path
    r = client.get("/api/v1/workflows/999")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "workflow_run_not_found"
    assert body["request_id"]

    # 400 path
    r = client.post("/api/v1/workflows")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "missing_goal"

    # 422 path (missing required query)
    r = client.get("/api/v1/workflows", params={"limit": 0})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_error"

    # No internal stack trace leaked
    assert "traceback" not in r.text.lower()


def test_request_id_is_propagated_in_headers():
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    client = TestClient(app)
    r = client.get("/health", headers={"X-Request-ID": "my-id"})
    assert r.headers["X-Request-ID"] == "my-id"
    assert r.json()["request_id"] == "my-id"


def test_request_id_is_generated_when_absent():
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    client = TestClient(app)
    r = client.get("/health")
    rid = r.headers["X-Request-ID"]
    assert rid
    assert len(rid) == 32  # uuid4 hex
