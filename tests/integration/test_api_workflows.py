"""Integration tests for workflow run persistence."""

from __future__ import annotations

from fastapi.testclient import TestClient

from nexusai.app.db.repositories.workflow_run import WorkflowRunRepository
from nexusai.app.services.workflow import WorkflowService


def test_create_and_fetch_run(client: TestClient):
    r = client.post("/api/v1/workflows", params={"goal": "Research local LLM options"})
    assert r.status_code == 200
    run = r.json()["run"]
    assert run["goal"] == "Research local LLM options"
    assert run["status"] == "pending"
    assert run["steps"] == []

    fetched = client.get(f"/api/v1/workflows/{run['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["run"]["goal"] == "Research local LLM options"


def test_create_run_requires_goal(client: TestClient):
    r = client.post("/api/v1/workflows")
    assert r.status_code == 400
    body = r.json()
    assert body["error"]["code"] == "missing_goal"
    assert body["error"]["details"]["parameter"] == "goal"
    assert body["request_id"]


def test_list_runs(client: TestClient):
    client.post("/api/v1/workflows", params={"goal": "A"})
    client.post("/api/v1/workflows", params={"goal": "B"})
    body = client.get("/api/v1/workflows").json()
    assert body["total"] == 2
    assert len(body["runs"]) == 2
    # Most recent first
    assert body["runs"][0]["id"] > body["runs"][1]["id"]


def test_list_runs_pagination(client: TestClient):
    for i in range(3):
        client.post("/api/v1/workflows", params={"goal": f"goal {i}"})
    body = client.get("/api/v1/workflows", params={"limit": 2}).json()
    assert len(body["runs"]) == 2
    assert body["total"] == 3


def test_get_missing_run_returns_404(client: TestClient):
    r = client.get("/api/v1/workflows/424242")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "workflow_run_not_found"


def test_delete_run(client: TestClient):
    created = client.post("/api/v1/workflows", params={"goal": "delete me"}).json()["run"]
    r = client.delete(f"/api/v1/workflows/{created['id']}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    assert client.get(f"/api/v1/workflows/{created['id']}").status_code == 404


def test_filter_by_condition(client: TestClient):
    client.post("/api/v1/workflows", params={"goal": "A", "condition": "A"})
    client.post("/api/v1/workflows", params={"goal": "B", "condition": "B"})
    body = client.get("/api/v1/workflows", params={"condition": "A"}).json()
    assert body["total"] == 1
    assert body["runs"][0]["condition"] == "A"


def test_repository_add_step_and_persist(db_session):
    repo = WorkflowRunRepository(db_session)
    run = repo.create("goal with steps", request_id="req-1", condition="C")
    db_session.commit()

    repo.add_step(
        run.id,
        0,
        step_id="s1",
        step_type="tool_call",
        tool="search",
        input_data='{"q": "x"}',
        output_data='{"hits": 3}',
        verification_result="pass",
    )
    db_session.commit()

    reloaded = repo.get(run.id)
    assert reloaded is not None
    assert len(reloaded.steps) == 1
    assert reloaded.steps[0].tool == "search"
    assert reloaded.steps[0].verification_result == "pass"


def test_repository_update_run_status(db_session):
    repo = WorkflowRunRepository(db_session)
    run = repo.create("goal", request_id="r")
    db_session.commit()
    updated = repo.update_status(
        run.id, status="completed", terminal_state="success", execution_time_ms=1234
    )
    db_session.commit()
    assert updated is not None
    assert updated.status == "completed"
    assert updated.terminal_state == "success"
    assert updated.execution_time_ms == 1234


def test_service_to_dict_includes_steps(db_session):
    service = WorkflowService(db_session)
    run = service.create_run("service goal", request_id="r2", condition="B")
    service.add_step(run.id, 0, tool="read_file", verification_result="fail")
    service.commit()
    payload = service.to_dict(service.get_run(run.id))
    assert payload["condition"] == "B"
    assert len(payload["steps"]) == 1
    assert payload["steps"][0]["verification_result"] == "fail"


def test_deleting_run_cascades_steps(db_session):
    repo = WorkflowRunRepository(db_session)
    run = repo.create("cascade", request_id="r")
    repo.add_step(run.id, 0, tool="t")
    db_session.commit()
    run_id = run.id
    assert repo.delete(run_id)
    db_session.commit()
    assert repo.get(run_id) is None
    assert repo.list_steps(run_id) == []
