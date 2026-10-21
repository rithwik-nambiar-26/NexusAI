"""Integration tests for the health and system status endpoints."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nexusai.app.config import Settings


def test_health_returns_ok_when_database_reachable(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "NexusAI"
    assert body["version"] == "0.1.0"
    assert body["environment"] == "testing"
    assert body["checks"]["database"] == "ok"
    assert body["request_id"]


def test_health_reports_unavailable_optional_services(client: TestClient):
    body = client.get("/health").json()
    # Ollama and ChromaDB are not configured, so they must not be claimed available.
    assert body["checks"]["ollama"] == "unavailable"
    assert body["checks"]["chromadb"] == "unavailable"


def test_health_is_unhealthy_when_database_unavailable(client_factory, tmp_path):
    """Health must report unhealthy rather than lying when the DB is broken.

    A file is placed where a directory would need to be, so the engine
    cannot be created and the health check must notice.
    """
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("this is a file, not a directory")
    settings = Settings(
        database_url=f"sqlite:///{blocker / 'nexusai.db'}",
        environment="testing",
    )
    client = client_factory(settings)
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "unhealthy"
    assert body["checks"]["database"] == "unavailable"


def test_system_status_shape(client: TestClient):
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    body = response.json()
    assert body["app"] == "NexusAI"
    names = {svc["name"] for svc in body["services"]}
    assert {"database", "ollama", "chromadb"} == names
    assert body["limits"]["max_retry_budget"] == 2
    assert body["request_id"]


def test_system_status_does_not_claim_unavailable_services(client: TestClient):
    body = client.get("/api/v1/system/status").json()
    for svc in body["services"]:
        if svc["name"] in {"ollama", "chromadb"}:
            assert svc["available"] is False
            assert svc["configured"] is False
            assert "not configured" in svc["detail"].lower()


def test_openapi_schema_is_generated(client: TestClient):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    schema = response.json()
    assert "/health" in schema["paths"]
    assert "/api/v1/system/status" in schema["paths"]
    assert "/api/v1/workflows" in schema["paths"]


def test_docs_endpoint_available(client: TestClient):
    assert client.get("/docs").status_code == 200
