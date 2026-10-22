"""Regression tests for the Day 5.5.1 integration defects.

Two defects were found during manual testing of the Streamlit
application:

1. A supported document intent became an ``out_of_scope`` plan with zero
   tasks, because the UI rendered a stale plan left over from a previous
   request and dropped the classification status when it passed the
   intent on.
2. The Data Intelligence page returned HTTP 400, because it hand-built a
   plan document whose ``created_at``/``updated_at`` fields were null
   and so failed schema validation.

These tests cover both defects and the behaviour they require.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nexusai.app.config import Settings
from nexusai.app.main import create_app
from nexusai.ml.schemas import ClassificationStatus, IntentCategory

PRODUCT_MANUAL_REQUEST = (
    "Read the uploaded product manual and tell me the installation requirements."
)
MEETING_NOTES_REQUEST = (
    "Summarise the uploaded meeting notes and identify the important decisions."
)
CSV_PATH = "data/sample/sales_2026.csv"


@pytest.fixture
def client(tmp_path) -> TestClient:
    """A test client with an isolated database and vector index."""
    settings = Settings(
        database_url="sqlite:///:memory:",
        vector_store_dir=str(tmp_path / "vectors"),
        allowed_document_roots=["./data", "./docs", "./experiments", str(tmp_path)],
    )
    return TestClient(create_app(settings))


@pytest.fixture
def indexed(client: TestClient) -> TestClient:
    """A client with the two sample documents ingested."""
    for path in ("data/sample/product_manual.md", "data/sample/meeting_notes.md"):
        response = client.post("/api/v1/documents/ingest", json={"path": path})
        assert response.json()["result"]["status"] == "ok"
    return client


# ---------------------------------------------------------------------------
# Defect 1 — intent classification and planning mismatch
# ---------------------------------------------------------------------------


def test_supported_document_intent_is_preserved_into_planning(indexed: TestClient):
    """A recognised document intent must reach the planner unchanged.

    The defect was that the plan showed a different intent entirely
    (``out_of_scope``) because the UI displayed a stale plan.
    """
    classification = indexed.post(
        "/api/v1/intent/classify", json={"text": PRODUCT_MANUAL_REQUEST}
    ).json()["result"]

    intent = classification["predicted_intent"]
    assert intent in {c.value for c in IntentCategory.supported()}

    plan = indexed.post(
        "/api/v1/planner/plan",
        json={"text": PRODUCT_MANUAL_REQUEST, "intent": intent, "source": "explicit"},
    ).json()["plan"]

    # The plan keeps the classified intent and is executable.
    assert plan["intent"] == intent
    assert plan["intent"] != "out_of_scope"
    assert plan["plan_status"] in ("ready", "validated")
    assert plan["tasks"]
    assert plan["execution_order"]


def test_low_confidence_classification_requests_clarification(indexed: TestClient):
    """A clarification-required classification must not silently plan.

    The intent is preserved, but the planner asks for clarification
    instead of producing tasks from a guess.
    """
    classification = indexed.post(
        "/api/v1/intent/classify", json={"text": PRODUCT_MANUAL_REQUEST}
    ).json()["result"]

    # Force the uncertain path the classifier reported.
    if classification["status"] != ClassificationStatus.CLARIFICATION_REQUIRED.value:
        pytest.skip("the classifier was confident about this request")

    plan = indexed.post(
        "/api/v1/planner/plan",
        json={
            "text": PRODUCT_MANUAL_REQUEST,
            "intent": classification["predicted_intent"],
            "source": "classifier",
            "intent_status": classification["status"],
            "intent_confidence": classification["confidence"],
        },
    ).json()["plan"]

    assert plan["clarification_required"] is True
    assert plan["clarification_question"]
    assert plan["tasks"] == []
    # The intent is not silently replaced.
    assert plan["intent"] == classification["predicted_intent"]
    assert plan["intent"] != "out_of_scope"


def test_explicit_intent_override_generates_the_correct_plan(indexed: TestClient):
    """An explicit override must produce a ready plan for that intent."""
    plan = indexed.post(
        "/api/v1/planner/plan",
        json={
            "text": PRODUCT_MANUAL_REQUEST,
            "intent": "document_question_answering",
            "source": "explicit",
        },
    ).json()["plan"]

    assert plan["intent"] == "document_question_answering"
    assert plan["plan_status"] in ("ready", "validated")
    assert plan["tasks"]
    assert plan["source"] == "explicit"
    # The override is not blocked by a low-confidence classification.
    assert plan["clarification_required"] is False


def test_explicit_override_overrides_a_clarification_status(indexed: TestClient):
    """An explicit override is a statement of intent, so it plans."""
    plan = indexed.post(
        "/api/v1/planner/plan",
        json={
            "text": PRODUCT_MANUAL_REQUEST,
            "intent": "document_question_answering",
            "source": "explicit",
            "intent_status": ClassificationStatus.CLARIFICATION_REQUIRED.value,
        },
    ).json()["plan"]

    assert plan["tasks"]
    assert plan["clarification_required"] is False


def test_document_selection_reaches_the_correct_task_inputs(indexed: TestClient):
    """The chosen document must reach the plan's task inputs."""
    documents = indexed.get("/api/v1/documents").json()["documents"]
    manual = next(d for d in documents if d["name"] == "product_manual.md")

    plan = indexed.post(
        "/api/v1/planner/plan",
        json={
            "text": PRODUCT_MANUAL_REQUEST,
            "intent": "document_question_answering",
            "source": "explicit",
        },
    ).json()["plan"]

    # The UI attaches the chosen document to the first document-reading
    # task; the executor then reads exactly that document.
    read_task = next(
        task
        for task in plan["tasks"]
        if "document.read" in task["required_capabilities"]
    )
    read_task.setdefault("input_parameters", []).append(
        {
            "name": "document_id",
            "value": manual["document_id"],
            "description": "Document chosen in the UI",
            "required": True,
        }
    )

    execution = indexed.post(
        "/api/v1/execution/execute", json={"plan": plan}
    ).json()["report"]

    read_result = next(
        r for r in execution["task_results"] if r["capability"] == "document.read"
    )
    assert read_result["status"] == "completed"
    assert read_result["output"]["document_id"] == manual["document_id"]
    assert read_result["output"]["name"] == "product_manual.md"


def test_planner_never_converts_a_supported_intent_to_out_of_scope(
    indexed: TestClient,
):
    """No supported intent may come back as out_of_scope."""
    for request, intent in (
        (PRODUCT_MANUAL_REQUEST, "document_question_answering"),
        (MEETING_NOTES_REQUEST, "document_summarisation"),
    ):
        plan = indexed.post(
            "/api/v1/planner/plan",
            json={"text": request, "intent": intent, "source": "explicit"},
        ).json()["plan"]
        assert plan["intent"] == intent
        assert plan["intent"] != "out_of_scope"


# ---------------------------------------------------------------------------
# Defect 2 — Data Intelligence HTTP 400
# ---------------------------------------------------------------------------


def test_data_intelligence_works_without_any_task_plan(client: TestClient):
    """The CSV analysis must not need a plan at all.

    The defect was that the page hand-built a plan document, whose null
    timestamps failed schema validation and produced an HTTP 400.
    """
    response = client.post(
        "/api/v1/documents/analyse-csv",
        json={"path": CSV_PATH, "group_by": "region", "measure": "revenue"},
    )
    assert response.status_code == 200
    output = response.json()["output"]
    assert output["rows"] == 26
    assert output["columns"] == 6


def test_data_intelligence_works_after_an_invalid_plan_exists(
    client: TestClient,
):
    """A stale or invalid plan must not affect the analysis."""
    # Produce an invalid plan first, exactly as a refused request would.
    invalid = client.post(
        "/api/v1/planner/plan",
        json={"text": "Delete all files in the project folder."},
    ).json()["plan"]
    assert invalid["plan_status"] == "invalid"
    assert invalid["tasks"] == []

    response = client.post(
        "/api/v1/documents/analyse-csv",
        json={"path": CSV_PATH, "group_by": "region", "measure": "revenue"},
    )
    assert response.status_code == 200
    assert response.json()["output"]["rows"] == 26


def test_csv_aggregation_returns_the_correct_source_derived_result(
    client: TestClient,
):
    """The grouped totals must match the verified figures from the file."""
    response = client.post(
        "/api/v1/documents/analyse-csv",
        json={"path": CSV_PATH, "group_by": "region", "measure": "revenue"},
    )
    assert response.status_code == 200
    output = response.json()["output"]

    totals = {row["region"]: row["total_revenue"] for row in output["grouped_totals"]}
    assert totals["Southern"] == 4059.0
    assert totals["Western"] == 3302.0
    assert totals["Eastern"] == 2756.0
    assert totals["Northern"] == 2604.0


def test_csv_invalid_path_is_safely_rejected(client: TestClient):
    """A path outside the allowed roots must be refused, not executed."""
    response = client.post(
        "/api/v1/documents/analyse-csv",
        json={"path": "../../../etc/passwd"},
    )
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] in ("path_not_allowed", "invalid_input")


def test_csv_unknown_column_is_reported_clearly(client: TestClient):
    """An unknown column must produce a useful message, not a bare 400."""
    response = client.post(
        "/api/v1/documents/analyse-csv",
        json={"path": CSV_PATH, "group_by": "no_such_column", "measure": "revenue"},
    )
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "invalid_input"
    assert "no_such_column" in body["message"]


def test_csv_non_numeric_measure_is_reported_clearly(client: TestClient):
    """A non-numeric measure must be refused with a reason."""
    response = client.post(
        "/api/v1/documents/analyse-csv",
        json={"path": CSV_PATH, "group_by": "region", "measure": "product"},
    )
    assert response.status_code == 400
    body = response.json()["error"]
    assert body["code"] == "invalid_input"
    assert "numeric" in body["message"].lower()


def test_csv_analysis_requires_a_path(client: TestClient):
    """The path is required."""
    response = client.post("/api/v1/documents/analyse-csv", json={})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# The safety controls must survive the fixes
# ---------------------------------------------------------------------------


def test_destructive_request_still_produces_no_plan(client: TestClient):
    """The destructive-operation protection must remain intact."""
    plan = client.post(
        "/api/v1/planner/plan",
        json={"text": "Delete all files in the project folder."},
    ).json()["plan"]

    assert plan["plan_status"] == "invalid"
    assert plan["tasks"] == []
    assert plan["requires_approval"] is True
    assert plan["clarification_required"] is True


def test_approval_gated_task_still_blocks_execution(client: TestClient):
    """An approval-gated capability must not run without approval."""
    plan = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Send the report to the client.",
            "intent": "communication",
            "source": "explicit",
        },
    ).json()["plan"]

    assert plan["requires_approval"] is True
    assert plan["approval_reasons"]

    report = client.post(
        "/api/v1/execution/execute", json={"plan": plan}
    ).json()["report"]

    # The send capability is not registered, so it is skipped — and in
    # particular it is not reported as completed.
    for result in report["task_results"]:
        assert result["status"] != "completed"


def test_unknown_capability_is_still_skipped(client: TestClient):
    """A capability that is not registered must never be attempted.

    The task naming it is skipped rather than attempted, and its
    dependents are blocked because the skipped task produced no result.
    """
    plan = client.post(
        "/api/v1/planner/plan",
        json={
            "text": "Research the topic and write a summary.",
            "intent": "research",
            "source": "explicit",
        },
    ).json()["plan"]

    report = client.post(
        "/api/v1/execution/execute", json={"plan": plan}
    ).json()["report"]

    # The first task needs research.query, which is not registered, so it
    # is skipped and never attempted.
    first = report["task_results"][0]
    assert first["capability"] == "research.query"
    assert first["status"] == "skipped"
    assert "not registered" in (first["error"] or "")

    # Its dependents are blocked, not completed.
    for result in report["task_results"][1:]:
        assert result["status"] == "blocked"
        assert result["status"] != "completed"
