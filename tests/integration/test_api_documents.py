"""Integration tests for the document intelligence API routes."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from tests.unit.rag import fixtures

from nexusai.app.config import Settings
from nexusai.app.main import create_app


@pytest.fixture
def client(tmp_path) -> TestClient:
    """Create a test client with an isolated database and vector index."""
    settings = Settings(
        database_url="sqlite:///:memory:",
        vector_store_dir=str(tmp_path / "vectors"),
    )
    app = create_app(settings)
    return TestClient(app)


@pytest.fixture
def document(tmp_path):
    """Return a Markdown fixture path."""
    return fixtures.write_markdown(tmp_path / "widget.md")


def test_ingest_document_endpoint(client: TestClient, document):
    """Test POST /api/v1/documents/ingest."""
    response = client.post("/api/v1/documents/ingest", json={"path": str(document)})

    assert response.status_code == 200
    data = response.json()
    assert "result" in data
    assert "request_id" in data
    assert data["result"]["status"] == "ok"
    assert data["result"]["chunk_count"] > 0


def test_ingest_duplicate_is_reported(client: TestClient, document):
    """Test that a duplicate ingestion is reported."""
    client.post("/api/v1/documents/ingest", json={"path": str(document)})
    response = client.post("/api/v1/documents/ingest", json={"path": str(document)})

    assert response.status_code == 200
    assert response.json()["result"]["duplicate"] is True


def test_ingest_unsupported_format(client: TestClient, tmp_path):
    """Test that an unsupported format is reported, not a server error."""
    path = tmp_path / "data.xyz"
    path.write_text("hello", encoding="utf-8")

    response = client.post("/api/v1/documents/ingest", json={"path": str(path)})
    assert response.status_code == 200
    assert response.json()["result"]["status"] == "unsupported_format"


def test_ingest_text_endpoint(client: TestClient):
    """Test POST /api/v1/documents/ingest-text."""
    response = client.post(
        "/api/v1/documents/ingest-text",
        json={"text": "# Title\n\nThe widget warranty is 12 months.", "name": "inline.md"},
    )

    assert response.status_code == 200
    assert response.json()["result"]["status"] == "ok"


def test_ingest_rejects_empty_path(client: TestClient):
    """Test that an empty path is rejected by validation."""
    response = client.post("/api/v1/documents/ingest", json={"path": ""})
    assert response.status_code == 422


def test_list_documents_endpoint(client: TestClient, document):
    """Test GET /api/v1/documents."""
    client.post("/api/v1/documents/ingest", json={"path": str(document)})
    response = client.get("/api/v1/documents")

    assert response.status_code == 200
    data = response.json()
    assert "documents" in data
    assert data["chunk_count"] > 0
    assert data["documents"][0]["name"] == "widget.md"


def test_retrieve_endpoint(client: TestClient, document):
    """Test POST /api/v1/documents/retrieve."""
    client.post("/api/v1/documents/ingest", json={"path": str(document)})
    response = client.post(
        "/api/v1/documents/retrieve",
        json={"query": "warranty coverage", "top_k": 3},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["count"] >= 1
    assert data["results"][0]["source_reference"]
    assert data["results"][0]["chunk"]["text"]


def test_retrieve_rejects_empty_query(client: TestClient):
    """Test that an empty query is rejected."""
    response = client.post("/api/v1/documents/retrieve", json={"query": ""})
    assert response.status_code == 422


def test_answer_endpoint(client: TestClient, document):
    """Test POST /api/v1/documents/answer."""
    client.post("/api/v1/documents/ingest", json={"path": str(document)})
    response = client.post(
        "/api/v1/documents/answer",
        json={"question": "What is the warranty period?"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert answer["status"] == "answered"
    assert answer["evidence"]
    assert answer["citations"]


def test_answer_endpoint_insufficient_evidence(client: TestClient, document):
    """Test that an unanswerable question is explicit."""
    client.post("/api/v1/documents/ingest", json={"path": str(document)})
    response = client.post(
        "/api/v1/documents/answer",
        json={"question": "What is the population of Reykjavik in 1990?"},
    )

    assert response.status_code == 200
    answer = response.json()["answer"]
    assert answer["status"] == "insufficient_evidence"
    assert answer["answer_text"] == ""
    assert answer["insufficient_reason"]


def test_answer_endpoint_without_documents(client: TestClient):
    """Test that answering with an empty index is explicit."""
    response = client.post("/api/v1/documents/answer", json={"question": "anything?"})
    assert response.status_code == 200
    assert response.json()["answer"]["status"] == "no_documents"


def test_summarise_endpoint(client: TestClient, document):
    """Test POST /api/v1/documents/summarise."""
    client.post("/api/v1/documents/ingest", json={"path": str(document)})
    response = client.post("/api/v1/documents/summarise", json={})

    assert response.status_code == 200
    summary = response.json()["summary"]
    assert summary["status"] == "answered"
    assert summary["citations"]


def test_capabilities_endpoint(client: TestClient):
    """Test GET /api/v1/documents/capabilities."""
    response = client.get("/api/v1/documents/capabilities")

    assert response.status_code == 200
    capabilities = response.json()["capabilities"]
    assert "document.read" in capabilities
    assert "document.extract" in capabilities
    assert "llm.summarise" in capabilities


def test_openapi_schema_includes_document_routes(client: TestClient):
    """Test that the document routes appear in the OpenAPI schema."""
    response = client.get("/openapi.json")
    assert response.status_code == 200
    paths = response.json()["paths"]
    assert "/api/v1/documents/ingest" in paths
    assert "/api/v1/documents/answer" in paths
    assert "/api/v1/documents/retrieve" in paths


def test_existing_endpoints_still_work(client: TestClient):
    """Test that the earlier endpoints are unaffected."""
    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/system/status").status_code == 200
    assert client.get("/api/v1/intent/intents").status_code == 200
    assert client.get("/api/v1/planner/status").status_code == 200
    assert client.get("/api/v1/workflows").status_code == 200
