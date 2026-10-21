"""Tests for intent classification API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app


@pytest.fixture
def client() -> TestClient:
    """Create test client with in-memory database."""
    app = create_app(Settings(database_url="sqlite:///:memory:"))
    return TestClient(app)


def test_classify_intent_endpoint(client: TestClient):
    """Test POST /api/v1/intent/classify endpoint."""
    response = client.post(
        "/api/v1/intent/classify",
        json={"text": "Summarize the product manual"},
    )

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "request_id" in data

    result = data["result"]
    assert "original_request" in result
    assert "predicted_intent" in result
    assert "confidence" in result
    assert "status" in result
    assert "all_scores" in result


def test_classify_intent_empty_text(client: TestClient):
    """Test classify endpoint with empty text."""
    response = client.post(
        "/api/v1/intent/classify",
        json={"text": ""},
    )

    assert response.status_code == 422  # Validation error


def test_classify_intent_missing_text(client: TestClient):
    """Test classify endpoint with missing text field."""
    response = client.post(
        "/api/v1/intent/classify",
        json={},
    )

    assert response.status_code == 422  # Validation error


def test_list_intents_endpoint(client: TestClient):
    """Test GET /api/v1/intent/intents endpoint."""
    response = client.get("/api/v1/intent/intents")

    assert response.status_code == 200
    data = response.json()
    assert "intents" in data
    assert "request_id" in data

    intents = data["intents"]
    assert len(intents) == 12

    # Check structure
    for intent in intents:
        assert "category" in intent
        assert "supported" in intent
        assert isinstance(intent["supported"], bool)


def test_classifier_status_endpoint(client: TestClient):
    """Test GET /api/v1/intent/status endpoint."""
    response = client.get("/api/v1/intent/status")

    assert response.status_code == 200
    data = response.json()
    assert "available" in data
    assert "model_path" in data
    assert "request_id" in data
    assert isinstance(data["available"], bool)


def test_classify_with_context(client: TestClient):
    """Test classify endpoint with context."""
    response = client.post(
        "/api/v1/intent/classify",
        json={"text": "Summarize the document", "context": {"user_id": "123"}},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["original_request"] == "Summarize the document"
